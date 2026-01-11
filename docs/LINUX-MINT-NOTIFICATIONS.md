# Linux Mint Notification Fix

## Issue

On Linux Mint (and some other distributions), notifications don't appear after inserting an unencrypted USB drive. This is due to a boot-time race condition where the USB Enforcer daemon starts before the DBus system service is fully available.

## Symptoms

- No notifications when inserting USB drives
- The daemon logs show: `WARNING pydbus not available; DBus API disabled`
- The UI service repeatedly restarts with: `Daemon DBus service not available; exiting UI bridge`
- `busctl --system list | grep UsbEnforcer` returns nothing

## Root Cause

The `usb-enforcerd.service` was starting before `dbus.service` was ready, causing the DBus connection to fail. Once failed at startup, the daemon wouldn't retry the connection.

## Fixes Applied

### 1. Updated systemd Service Dependencies

Modified `/deploy/systemd/usb-enforcerd.service` to wait for DBus:

```ini
[Unit]
Description=USB Encryption Enforcer DLP daemon
After=network.target dbus.service
Wants=systemd-udevd.service dbus.service
```

The key changes:
- Added `dbus.service` to the `After=` directive (ensures daemon starts after DBus)
- Added `dbus.service` to the `Wants=` directive (declares dependency on DBus)

### 2. Improved Error Handling

Enhanced the DBus connection code in `src/usb_enforcer/dbus_api.py` to:
- Catch exceptions when connecting to the system bus
- Log more specific error messages
- Gracefully degrade if DBus is unavailable

## Quick Fix for Existing Installations

If you're experiencing this issue right now, simply restart the daemon:

```bash
sudo systemctl restart usb-enforcerd.service
```

The UI service will automatically reconnect within a few seconds.

## Applying the Permanent Fix

To apply the permanent fix to your installation:

1. **Update the service file:**
   ```bash
   sudo cp deploy/systemd/usb-enforcerd.service /etc/systemd/system/usb-enforcerd.service
   sudo systemctl daemon-reload
   ```

2. **Verify the fix:**
   ```bash
   # Check that the daemon has DBus enabled
   sudo journalctl -u usb-enforcerd.service -n 20 | grep -i dbus
   # Should show: "DBus service published at org.seravault.UsbEnforcer"
   
   # Verify DBus service is registered
   busctl --system list | grep UsbEnforcer
   # Should show: org.seravault.UsbEnforcer
   
   # Check UI service is running
   systemctl --user status usb-enforcer-ui.service
   # Should show: Active: active (running)
   ```

3. **Test notifications:**
   Insert an unencrypted USB drive. You should see a notification saying:
   - **Title:** "USB mounted read-only"
   - **Body:** "Writing requires encryption."
   - **Action:** "Encrypt drive…"

## Verification Commands

### Check Daemon Status
```bash
sudo systemctl status usb-enforcerd.service
sudo journalctl -u usb-enforcerd.service -n 20
```

Look for: `INFO DBus service published at org.seravault.UsbEnforcer`

### Check UI Service Status
```bash
systemctl --user status usb-enforcer-ui.service
journalctl --user -u usb-enforcer-ui.service -n 20
```

Look for: `usb-enforcer-ui listening for events...`

### Check DBus Registration
```bash
busctl --system list | grep UsbEnforcer
```

Should return: `org.seravault.UsbEnforcer`

### Monitor Live Events
```bash
# Terminal 1: Watch daemon logs
sudo journalctl -u usb-enforcerd.service -f

# Terminal 2: Watch UI service logs  
journalctl --user -u usb-enforcer-ui.service -f

# Terminal 3: Insert a USB drive
# You should see events in both terminals
```

## Related Files

- **Service file:** `deploy/systemd/usb-enforcerd.service`
- **DBus API:** `src/usb_enforcer/dbus_api.py`
- **UI Service:** `src/usb_enforcer/usb_enforcer_ui.py`
- **General troubleshooting:** `docs/UBUNTU-NOTIFICATIONS.md`

## Additional Notes

This issue is similar to the Ubuntu notification issue documented in `UBUNTU-NOTIFICATIONS.md`, but requires the additional systemd dependency fix. The Ubuntu fix (restarting the services) works temporarily, but the systemd configuration ensures the problem doesn't recur on reboot.

## Distribution-Specific Behavior

- **Fedora:** Usually works out of the box (user services start reliably)
- **Ubuntu/Debian:** May require logout/login for UI service to start
- **Linux Mint:** Requires both the DBus dependency fix AND may need a manual daemon restart on first install

After applying this fix, notifications should work correctly on Linux Mint without manual intervention after reboots.

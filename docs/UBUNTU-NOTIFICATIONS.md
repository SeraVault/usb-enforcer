# Ubuntu/Debian Notification Setup

## Issue: Notifications Not Appearing on Ubuntu

If you've installed USB Enforcer on Ubuntu (or other Debian-based distributions) and notifications aren't appearing when USB drives are inserted, this is typically because the user notification service (`usb-enforcer-ui.service`) is not running.

### Quick Fix

Start the service manually:

```bash
systemctl --user start usb-enforcer-ui.service
```

The service will then run until you log out. It should start automatically on your next login.

### Verify Service Status

Check if the service is running:

```bash
systemctl --user status usb-enforcer-ui.service
```

You should see `Active: active (running)`. If you see `Active: inactive (dead)`, the service is not running.

### Why This Happens

**Difference between Fedora and Ubuntu:**
- On **Fedora**, user services tied to `graphical-session.target` typically start immediately after installation
- On **Ubuntu**, user services may require a logout/login cycle or manual start after first install
- This is due to differences in how systemd user sessions are managed across distributions

The service is properly installed and enabled, but systemd's user session needs to be aware of it. After the first manual start or next login, it will start automatically.

### Permanent Solution

The service is already configured to start automatically on login. If it's not starting:

1. **Ensure the service is enabled:**
   ```bash
   systemctl --user enable usb-enforcer-ui.service
   systemctl --user is-enabled usb-enforcer-ui.service  # Should output "enabled"
   ```

2. **Check the service file location:**
   ```bash
   ls -la /etc/systemd/user/graphical-session.target.wants/usb-enforcer-ui.service
   ```
   
   This should be a symlink to `/usr/lib/systemd/user/usb-enforcer-ui.service`.

3. **Reload systemd if needed:**
   ```bash
   systemctl --user daemon-reload
   ```

4. **Log out and log back in** - This ensures the graphical session target properly pulls in the service.

### Testing Notifications

Once the service is running, test it by:

1. **Insert an unencrypted USB drive** - You should see a notification saying "USB mounted read-only" with an "Encrypt drive…" action
2. **Insert an encrypted USB drive** - You should see "Encrypted USB detected" with an "Unlock drive…" action

### Monitoring the Service

Watch real-time logs to see when events are received:

```bash
journalctl --user -u usb-enforcer-ui.service -f
```

Plug in a USB drive and you should see messages like:
```
[handle_event] event=enforce action=block_rw devnode=/dev/sdb1
[notify] showing notification with encrypt action for /dev/sdb1
```

### Common Issues

**No notification daemon available:**
```bash
# Check if notification service is running
gdbus introspect --session --dest org.freedesktop.Notifications --object-path /org/freedesktop/Notifications
```

If this fails, your desktop environment's notification daemon isn't running. This is required for notifications to work.

**DBus connection issues:**
```bash
# Check if the daemon is reachable
busctl --system list | grep UsbEnforcer
```

You should see `org.seravault.UsbEnforcer`. If not, check the system daemon:
```bash
sudo systemctl status usb-enforcerd.service
```

### Desktop Environment Compatibility

The notification system works on:
- ✅ **GNOME** (native)
- ✅ **KDE Plasma** (via freedesktop notifications)
- ✅ **XFCE** (requires `xfce4-notifyd`)
- ✅ **Cinnamon** (native)
- ✅ **MATE** (requires `mate-notification-daemon`)
- ✅ **Budgie** (native)

If you're using a minimal window manager without a notification daemon, install one:
```bash
# Ubuntu/Debian
sudo apt install notification-daemon
# or
sudo apt install dunst
```

### Advanced: Service Configuration

The service file is located at `/usr/lib/systemd/user/usb-enforcer-ui.service` and contains:

```ini
[Unit]
Description=USB Encryption Enforcer UI bridge (notifications)
After=graphical-session.target dbus.service
PartOf=graphical-session.target
Wants=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/lib/usb-enforcer/.venv/bin/python3 -u /usr/libexec/usb-enforcer-ui
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=graphical-session.target
```

Key points:
- **PartOf=graphical-session.target**: Service is tied to graphical session lifecycle
- **Restart=always**: Auto-restart on failure (changed from `on-failure` for better reliability)
- **RestartSec=3**: Wait 3 seconds before restarting (increased from 2 for stability)
- **WantedBy=graphical-session.target**: Start when graphical session starts

### Still Having Issues?

If notifications still don't work after following these steps:

1. Check the main daemon logs:
   ```bash
   sudo journalctl -u usb-enforcerd -n 100
   ```

2. Verify the daemon is detecting USB events:
   ```bash
   # In one terminal, watch logs
   sudo journalctl -u usb-enforcerd -f
   
   # In another terminal, plug in a USB drive
   ```
   
   You should see classification and enforcement messages.

3. Check if the UI service is receiving events:
   ```bash
   journalctl --user -u usb-enforcer-ui.service -f
   ```
   
   When you plug in a USB drive, you should see `[handle_event]` messages.

If the daemon logs show events but the UI service doesn't, there may be a DBus communication issue. Check that both services can access the session/system bus:

```bash
# For system daemon
sudo busctl list | grep UsbEnforcer

# For user service
busctl --user list
```

## Summary

**TL;DR for Ubuntu users:**
```bash
# After installing USB Enforcer, run this once:
systemctl --user start usb-enforcer-ui.service

# Or simply log out and log back in
```

The service will then work automatically on all future logins.

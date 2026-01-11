# Debug Commands for Fresh Installation

Run these commands on the Linux Mint machine where notifications and wizard aren't working:

## 1. Check if notification daemon is running
```bash
# Check if notification service is available on D-Bus
dbus-send --session --print-reply --dest=org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus.ListNames | grep -i notif

# Check what notification daemon is running (if any)
ps aux | grep -i notif
```

## 2. Check if usb-enforcer services are running
```bash
# Check daemon status
sudo systemctl status usb-enforcerd.service

# Check UI bridge status (runs as user)
systemctl --user status usb-enforcer-ui.service

# View daemon logs
sudo journalctl -u usb-enforcerd.service -n 50 --no-pager

# View UI bridge logs (this is crucial - it shows notification errors)
journalctl --user -u usb-enforcer-ui.service -n 50 --no-pager
```

## 3. Test notifications manually
```bash
# Test if notify-send works at all
notify-send "Test" "This is a test notification"

# Check if libnotify-bin is installed
dpkg -l | grep libnotify-bin

# Test D-Bus notification directly with Python
python3 -c "
import pydbus
from gi.repository import GLib
bus = pydbus.SessionBus()
notify = bus.get('org.freedesktop.Notifications', '/org/freedesktop/Notifications')
print('Notification ID:', notify.Notify('test-app', 0, '', 'Test Title', 'Test Body', [], {}, 5000))
"
```

## 4. Check wizard installation and permissions
```bash
# Check if wizard script exists and is executable
ls -la /usr/libexec/usb-enforcer-wizard

# Try to run wizard manually (as your user, not root)
/usr/libexec/usb-enforcer-wizard --help

# Check Python environment
/usr/libexec/usb-enforcer-wizard --version 2>&1 || echo "Failed to run wizard"

# Check if GTK/GUI libraries are available
python3 -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk; print('GTK OK')"
python3 -c "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk; print('GTK4 OK')"
```

## 5. Check installed dependencies
```bash
# List all usb-enforcer related packages
dpkg -l | grep usb-enforcer

# Check for missing Python dependencies
python3 -c "import pydbus; print('pydbus:', pydbus.__version__)"
python3 -c "import pyudev; print('pyudev:', pyudev.__version__)"
python3 -c "from gi.repository import GLib; print('GLib OK')"
```

## 6. Check virtual environment (for bundled version)
```bash
# If using bundled version, check the venv
ls -la /usr/lib/usb-enforcer/.venv/

# Test if venv Python works
/usr/lib/usb-enforcer/.venv/bin/python3 --version

# Check venv has required packages
/usr/lib/usb-enforcer/.venv/bin/python3 -c "import pydbus, pyudev; print('Venv packages OK')"
```

## 7. Check D-Bus configuration
```bash
# Check if daemon D-Bus service is registered
dbus-send --system --print-reply --dest=org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus.ListNames | grep -i usb

# Check D-Bus config file
cat /etc/dbus-1/system.d/org.seravault.UsbEnforcer.conf
```

## 8. Test with a USB device
```bash
# Plug in a USB drive and watch logs in real-time
sudo journalctl -u usb-enforcerd.service -f
```

In another terminal:
```bash
# Watch UI service logs
journalctl --user -u usb-enforcer-ui.service -f
```

## 9. Check desktop environment session
```bash
# These variables need to be set for GUI apps
echo "DISPLAY=$DISPLAY"
echo "WAYLAND_DISPLAY=$WAYLAND_DISPLAY"
echo "XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR"
echo "DBUS_SESSION_BUS_ADDRESS=$DBUS_SESSION_BUS_ADDRESS"

# Check if you're in a graphical session
loginctl show-session $(loginctl | grep $(whoami) | awk '{print $1}') -p Type
```

## Most Likely Issues:

1. **UI service not running**: Check `systemctl --user status usb-enforcer-ui.service`
2. **No notification daemon**: Cinnamon should have one, but check `ps aux | grep -i notif`
3. **Python import errors**: Check venv or system Python can import pydbus/pyudev
4. **Missing GUI libraries**: Check GTK imports work
5. **Session bus not available**: The UI runs in user session and needs proper D-Bus session bus

## Quick First Check:
```bash
# Run this one-liner to get overview:
echo "=== Services ===" && \
sudo systemctl is-active usb-enforcerd && \
systemctl --user is-active usb-enforcer-ui && \
echo "=== UI Logs (last 10 lines) ===" && \
journalctl --user -u usb-enforcer-ui.service -n 10 --no-pager && \
echo "=== Test notification ===" && \
notify-send "Test" "Testing notifications"
```

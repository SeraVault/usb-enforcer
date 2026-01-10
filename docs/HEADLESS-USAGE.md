# USB Enforcer - Headless Usage Guide

This guide explains how to use USB Enforcer on headless systems (servers, systems without GUI) where the graphical wizard and notification UI are not available.

## Overview

USB Enforcer's core functionality works perfectly on headless systems:
- The **daemon** (`usb-enforcerd`) runs as a system service and enforces encryption policies automatically
- All operations are accessible via **DBus API** which can be called from command-line tools
- USB devices are **automatically detected** via udev
- Plaintext USB devices are **automatically blocked** (read-only) by the daemon
- The GTK wizard and notification UI are **optional** components

## Architecture on Headless Systems

- **Daemon**: `usb-enforcerd` runs as a systemd service, monitors udev events, and enforces policies
- **DBus API**: `org.seravault.UsbEnforcer` provides methods for listing devices, checking status, unlocking, and encrypting
- **Secret Socket**: `/run/usb-enforcer.sock` - UNIX socket for secure passphrase transmission
- **No GUI Required**: All operations can be performed via command-line DBus tools (`busctl`, `dbus-send`, `gdbus`, or Python scripts)

## Installation on Headless Systems

Install the package normally - the daemon will work without GUI components:

```bash
# RPM-based systems
sudo dnf install usb-enforcer-1.0.0-1.*.noarch.rpm

# Debian-based systems
sudo apt install ./usb-enforcer_1.0.0-1_all.deb
```

The daemon will start automatically. Verify it's running:

```bash
sudo systemctl status usb-enforcerd
```

## Command-Line Operations

### 1. Listing USB Devices

Use `busctl` to call the DBus API:

```bash
busctl call org.seravault.UsbEnforcer /org/seravault/UsbEnforcer \
  org.seravault.UsbEnforcer ListDevices
```

Or with Python:

```python
#!/usr/bin/env python3
import pydbus

bus = pydbus.SystemBus()
proxy = bus.get("org.seravault.UsbEnforcer", "/org/seravault/UsbEnforcer")
devices = proxy.ListDevices()

for device in devices:
    print(f"Device: {device.get('devnode')}")
    print(f"  Type: {device.get('device_type')}")
    print(f"  State: {device.get('state')}")
    print(f"  Filesystem: {device.get('fs_type')}")
    print()
```

### 2. Checking Device Status

Check a specific device:

```bash
busctl call org.seravault.UsbEnforcer /org/seravault/UsbEnforcer \
  org.seravault.UsbEnforcer GetDeviceStatus s "/dev/sdb1"
```

### 3. Unlocking an Encrypted USB Device

To unlock a LUKS2-encrypted USB device, you need to:

1. Send the passphrase via the secret socket (returns a token)
2. Call `RequestUnlock` via DBus with the token

**Python script for unlocking:**

```python
#!/usr/bin/env python3
"""Unlock an encrypted USB device from command line"""
import sys
import getpass
import pydbus
from usb_enforcer import secret_socket

def unlock_device(devnode):
    # Get passphrase from user
    passphrase = getpass.getpass(f"Enter passphrase for {devnode}: ")
    
    # Send passphrase via secret socket, get token
    token = secret_socket.send_secret("unlock", devnode, passphrase)
    
    # Call DBus method with token
    bus = pydbus.SystemBus()
    proxy = bus.get("org.seravault.UsbEnforcer", "/org/seravault/UsbEnforcer")
    result = proxy.RequestUnlock(devnode, "", token)
    
    print(f"Result: {result}")
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <devnode>")
        print(f"Example: {sys.argv[0]} /dev/sdb1")
        sys.exit(1)
    
    unlock_device(sys.argv[1])
```

Save as `unlock-usb.py` and run:

```bash
chmod +x unlock-usb.py
sudo python3 unlock-usb.py /dev/sdb1
```

### 4. Encrypting a USB Device

To encrypt a USB device with LUKS2:

**Python script for encryption:**

```python
#!/usr/bin/env python3
"""Encrypt a USB device from command line"""
import sys
import getpass
import pydbus
from usb_enforcer import secret_socket

def encrypt_device(devnode, label="EncryptedUSB", fs_type="exfat"):
    # Get passphrase from user (with confirmation)
    while True:
        passphrase = getpass.getpass(f"Enter passphrase for {devnode} (min 12 chars): ")
        if len(passphrase) < 12:
            print("Passphrase must be at least 12 characters")
            continue
        confirm = getpass.getpass("Confirm passphrase: ")
        if passphrase != confirm:
            print("Passphrases do not match")
            continue
        break
    
    # Confirm data destruction
    print(f"\nWARNING: This will DESTROY all data on {devnode}")
    confirm = input("Type 'yes' to continue: ")
    if confirm.lower() != "yes":
        print("Cancelled")
        return
    
    # Send passphrase via secret socket, get token
    token = secret_socket.send_secret("encrypt", devnode, passphrase)
    
    # Call DBus method with token
    bus = pydbus.SystemBus()
    proxy = bus.get("org.seravault.UsbEnforcer", "/org/seravault/UsbEnforcer")
    result = proxy.RequestEncrypt(devnode, "", token, fs_type, label)
    
    print(f"Result: {result}")
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <devnode> [label] [fs_type]")
        print(f"Example: {sys.argv[0]} /dev/sdb1 MyUSB exfat")
        print(f"Filesystem types: exfat (default), ext4, vfat")
        sys.exit(1)
    
    devnode = sys.argv[1]
    label = sys.argv[2] if len(sys.argv) > 2 else "EncryptedUSB"
    fs_type = sys.argv[3] if len(sys.argv) > 3 else "exfat"
    
    encrypt_device(devnode, label, fs_type)
```

Save as `encrypt-usb.py` and run:

```bash
chmod +x encrypt-usb.py
sudo python3 encrypt-usb.py /dev/sdb1 MySecureUSB exfat
```

### 5. Monitoring Events

Monitor USB device events in real-time:

```python
#!/usr/bin/env python3
"""Monitor USB Enforcer events from command line"""
from gi.repository import GLib
import pydbus

def on_event(fields):
    print(f"Event received:")
    for key, value in fields.items():
        print(f"  {key}: {value}")
    print()

bus = pydbus.SystemBus()
proxy = bus.get("org.seravault.UsbEnforcer", "/org/seravault/UsbEnforcer")

# Subscribe to Event signal
proxy.Event.connect(on_event)

print("Monitoring USB Enforcer events... (Ctrl+C to exit)")
loop = GLib.MainLoop()
try:
    loop.run()
except KeyboardInterrupt:
    print("\nExiting...")
```

Save as `monitor-events.py` and run:

```bash
sudo python3 monitor-events.py
```

## Workflow for Headless Systems

### Typical Use Case 1: Unlocking an Encrypted USB

1. **Plug in encrypted USB device**
2. **Check daemon detected it:**
   ```bash
   sudo journalctl -u usb-enforcerd -f
   ```
3. **List devices to find the devnode:**
   ```bash
   sudo python3 unlock-usb.py
   ```
4. **Unlock the device:**
   ```bash
   sudo python3 unlock-usb.py /dev/sdb1
   ```
5. **Mount the decrypted device:**
   ```bash
   udisksctl mount -b /dev/mapper/luks-<uuid>
   # Or use traditional mount:
   sudo mount /dev/mapper/luks-<uuid> /mnt/usb
   ```

### Typical Use Case 2: Encrypting a Plaintext USB

1. **Plug in plaintext USB device** (will be auto-blocked as read-only)
2. **Verify it's blocked:**
   ```bash
   sudo journalctl -u usb-enforcerd -f
   # Should see: "Setting read-only flag for plaintext device"
   ```
3. **Encrypt the device:**
   ```bash
   sudo python3 encrypt-usb.py /dev/sdb1 MyBackup exfat
   ```
4. **Device is now encrypted and can be unlocked/mounted**

### Typical Use Case 3: Automated Scripts

For automated workflows (backups, data transfers), create wrapper scripts:

```bash
#!/bin/bash
# automated-backup.sh - Unlock USB, backup, lock
set -e

DEVICE="/dev/sdb1"
PASSPHRASE="$1"
BACKUP_SRC="/data/to/backup"

# Unlock device
echo "$PASSPHRASE" | python3 - <<'EOF'
import sys
import pydbus
from usb_enforcer import secret_socket

passphrase = sys.stdin.read().strip()
devnode = "/dev/sdb1"

token = secret_socket.send_secret("unlock", devnode, passphrase)
bus = pydbus.SystemBus()
proxy = bus.get("org.seravault.UsbEnforcer", "/org/seravault/UsbEnforcer")
result = proxy.RequestUnlock(devnode, "", token)
print(result)
EOF

# Wait for device mapper
sleep 2

# Find and mount the decrypted device
MAPPER=$(ls /dev/mapper/luks-* | head -1)
MOUNT_POINT=$(udisksctl mount -b "$MAPPER" | awk '{print $NF}' | tr -d '.')

# Perform backup
rsync -av "$BACKUP_SRC" "$MOUNT_POINT/"

# Unmount
udisksctl unmount -b "$MAPPER"

echo "Backup complete!"
```

## Using Direct DBus Tools

For systems without Python, use `busctl` or `dbus-send`:

### List devices with busctl:
```bash
busctl call org.seravault.UsbEnforcer /org/seravault/UsbEnforcer \
  org.seravault.UsbEnforcer ListDevices
```

### Get device status:
```bash
busctl call org.seravault.UsbEnforcer /org/seravault/UsbEnforcer \
  org.seravault.UsbEnforcer GetDeviceStatus s "/dev/sdb1"
```

**Note:** For unlock/encrypt operations, you'll need to handle the secret socket communication, which is easier with Python or a custom shell/C program.

## Direct cryptsetup Commands (Advanced)

For emergency situations, you can bypass USB Enforcer and use `cryptsetup` directly:

```bash
# Unlock manually
sudo cryptsetup luksOpen /dev/sdb1 my-usb
sudo mount /dev/mapper/my-usb /mnt/usb

# When done
sudo umount /mnt/usb
sudo cryptsetup luksClose my-usb
```

**Warning:** Direct `cryptsetup` use bypasses USB Enforcer's logging and audit trail.

## Configuration for Headless Systems

Edit `/etc/usb-enforcer/config.toml`:

```toml
# Disable UI components (optional, they won't run anyway without X/Wayland)
# No specific setting needed - UI services won't start without display

# Adjust enforcement settings
[enforcement]
enforce_on_usb_only = true  # Only enforce on USB devices
allow_luks1_readonly = true  # Allow LUKS1 devices as read-only

# Set default filesystem for encryption
[encryption]
filesystem_type = "exfat"  # Or "ext4", "vfat"
min_passphrase_length = 16  # Increase for servers

# Argon2id KDF settings (more rounds for server use)
[kdf]
type = "argon2id"
time_cost = 8  # Increase from default 4 for better security
memory_cost = 1048576  # 1GB of RAM
parallel_threads = 4
```

## Systemd Service Management

```bash
# Check daemon status
sudo systemctl status usb-enforcerd

# View logs
sudo journalctl -u usb-enforcerd -f

# Restart daemon (e.g., after config changes)
sudo systemctl restart usb-enforcerd

# Disable UI service (if installed)
sudo systemctl disable --now usb-enforcer-ui
```

## Security Considerations for Headless Systems

1. **SSH Access**: When using USB Enforcer over SSH, ensure you're using key-based authentication
2. **Passphrase Security**: Avoid storing passphrases in shell history or scripts
   - Use `getpass` in Python
   - Use `read -s` in bash
   - Clear history: `history -c`
3. **Audit Logging**: All operations are logged to journald - review regularly
4. **Group Exemptions**: Consider exempting specific service accounts if needed (see [GROUP-EXEMPTIONS.md](GROUP-EXEMPTIONS.md))
5. **Socket Permissions**: The secret socket (`/run/usb-enforcer.sock`) is only accessible by root

## Troubleshooting

### Device not detected
```bash
# Check udev rules are loaded
udevadm control --reload-rules
udevadm trigger

# Check daemon is running
sudo systemctl status usb-enforcerd

# Monitor udev events
udevadm monitor --property
```

### DBus connection fails
```bash
# Check DBus service is registered
busctl list | grep UsbEnforcer

# Check daemon logs
sudo journalctl -u usb-enforcerd -n 50
```

### Unlock/Encrypt fails
```bash
# Check detailed logs
sudo journalctl -u usb-enforcerd -f

# Verify cryptsetup is available
which cryptsetup
cryptsetup --version  # Should be 2.4.0+

# Check device is actually LUKS encrypted
sudo cryptsetup luksDump /dev/sdb1
```

## Example Scripts Repository

Create a directory for helper scripts:

```bash
sudo mkdir -p /usr/local/sbin/usb-enforcer-cli
cd /usr/local/sbin/usb-enforcer-cli

# Create the unlock script
sudo tee unlock-usb.py << 'EOF'
[Include the Python unlock script from above]
EOF

# Create the encrypt script
sudo tee encrypt-usb.py << 'EOF'
[Include the Python encrypt script from above]
EOF

# Make executable
sudo chmod +x *.py
```

Add to PATH in `/etc/profile.d/usb-enforcer.sh`:
```bash
export PATH="/usr/local/sbin/usb-enforcer-cli:$PATH"
```

## Alternative: Pre-encrypted USB Workflow

For headless servers, consider encrypting USB devices on a desktop system first:

1. **On desktop**: Use the GTK wizard to encrypt USB device
2. **On server**: Simply unlock pre-encrypted devices

This approach provides a better UX for initial encryption while allowing headless unlock.

## Integration with System Scripts

### Udev Rule for Auto-unlock (Not Recommended)

While possible to auto-unlock devices via udev rules, this is **not recommended** as it defeats the security purpose. However, for specific trusted devices in secure environments:

```udev
# /etc/udev/rules.d/90-auto-unlock-trusted-usb.rules
# WARNING: This reduces security - use only for specific trusted devices
ACTION=="add", SUBSYSTEM=="block", ENV{ID_SERIAL}=="<specific-serial>", \
  RUN+="/usr/local/sbin/auto-unlock-usb.sh %k"
```

## See Also

- [Main README](../README.md) - Installation and overview
- [GROUP-EXEMPTIONS.md](GROUP-EXEMPTIONS.md) - Exempting specific users/groups
- [USB-ENFORCER.md](USB-ENFORCER.md) - Technical architecture details

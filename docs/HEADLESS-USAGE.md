# USB Enforcer - Headless Usage Guide

This guide explains how to use USB Enforcer on headless systems (servers, systems without GUI) where the graphical wizard and notification UI are not available.

## Overview

USB Enforcer's core functionality works perfectly on headless systems:
- The **daemon** (`usb-enforcerd`) runs as a system service and enforces encryption policies automatically
- All operations are accessible via **command-line interface** (`usb-enforcer-cli`)
- USB devices are **automatically detected** via udev
- Plaintext USB devices are **automatically blocked** (read-only) by the daemon
- The GTK wizard and notification UI are **optional** components

## Architecture on Headless Systems

- **Daemon**: `usb-enforcerd` runs as a systemd service, monitors udev events, and enforces policies
- **CLI Tool**: `usb-enforcer-cli` provides commands for listing devices, checking status, unlocking, and encrypting
- **DBus API**: `org.seravault.UsbEnforcer` provides the underlying API (can be called directly if needed)
- **Secret Socket**: `/run/usb-enforcer.sock` - UNIX socket for secure passphrase transmission

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

USB Enforcer provides a comprehensive CLI tool that simplifies all operations. The `usb-enforcer-cli` command is installed in `/usr/bin` and available system-wide.

### 1. Listing USB Devices

```bash
sudo usb-enforcer-cli list
```

Output:
```
Found 2 USB device(s):

1. /dev/sdb1
   Type: encrypted
   State: locked
   Filesystem: crypto_LUKS

2. /dev/sdc1
   Type: plaintext
   State: blocked
   Filesystem: vfat
```

For JSON output (useful for scripts):
```bash
sudo usb-enforcer-cli list --json
```

### 2. Checking Device Status

```bash
sudo usb-enforcer-cli status /dev/sdb1
```

Output:
```
Device: /dev/sdb1
Type: encrypted
State: locked
Filesystem: crypto_LUKS
Encrypted: True
Encryption type: luks2
```

### 3. Unlocking an Encrypted USB Device

```bash
sudo usb-enforcer-cli unlock /dev/sdb1
```

You'll be prompted securely for the passphrase (no echo). The device will be unlocked and mounted automatically.

**Non-interactive unlock** (not recommended for security):
```bash
sudo usb-enforcer-cli unlock /dev/sdb1 --passphrase "your-passphrase"
```

### 4. Encrypting a USB Device

**Warning: This will destroy all data on the device!**

```bash
sudo usb-enforcer-cli encrypt /dev/sdb1
```

You'll be prompted for:
- Passphrase (minimum 12 characters, with confirmation)
- Confirmation to destroy data

With options:
```bash
sudo usb-enforcer-cli encrypt /dev/sdb1 \
  --label "MySecureUSB" \
  --filesystem exfat \
  --yes  # Skip confirmation prompt
```

Available filesystems: `exfat` (default, cross-platform), `ext4` (Linux), `vfat` (FAT32)

### 5. Monitoring USB Device Events

Monitor events in real-time:

```bash
sudo usb-enforcer-cli monitor
```

Output:
```
Monitoring USB device events (Ctrl+C to stop)...

[2026-01-19 17:30:15] device_added: /dev/sdb1
  Action: encrypt_prompt

[2026-01-19 17:30:42] device_mounted: /dev/sdb1
  Mounted at: /media/user/MySecureUSB

[2026-01-19 17:31:05] unformatted_drive: /dev/sdc
  Suggested: luks2 + exfat
```

For JSON output:
```bash
sudo usb-enforcer-cli monitor --json
```

## CLI Help and Options

Get help on any command:

```bash
usb-enforcer-cli --help
usb-enforcer-cli list --help
usb-enforcer-cli unlock --help
usb-enforcer-cli encrypt --help
```

## Advanced: Direct DBus API Usage

If you need to integrate with other tools or scripts, you can call the DBus API directly.

### Using busctl

List devices:
```bash
busctl call org.seravault.UsbEnforcer /org/seravault/UsbEnforcer \
  org.seravault.UsbEnforcer ListDevices
```

Check device status:
```bash
busctl call org.seravault.UsbEnforcer /org/seravault/UsbEnforcer \
  org.seravault.UsbEnforcer GetDeviceStatus s "/dev/sdb1"
```

### Using Python with pydbus

**List devices:**

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

**Unlock device:**

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

## Workflow Examples for Headless Systems

### Typical Use Case 1: Unlocking an Encrypted USB

1. **Plug in encrypted USB device**
2. **Check daemon detected it:**
   ```bash
   sudo journalctl -u usb-enforcerd -f
   ```
3. **List devices:**
   ```bash
   sudo usb-enforcer-cli list
   ```
4. **Unlock the device:**
   ```bash
   sudo usb-enforcer-cli unlock /dev/sdb1
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
   sudo usb-enforcer-cli encrypt /dev/sdb1 --label MyBackup --filesystem exfat
   ```
4. **Device is now encrypted and can be unlocked/mounted**

### Typical Use Case 3: Automated Monitoring

Monitor device events in real-time during testing or troubleshooting:

```bash
# Monitor with human-readable output
sudo usb-enforcer-cli monitor

# Or with JSON output for parsing
sudo usb-enforcer-cli monitor --json
```

### Typical Use Case 4: Automated Scripts

For automated workflows (backups, data transfers), integrate the CLI into scripts:

```bash
#!/bin/bash
# automated-backup.sh - Unlock USB, backup, lock
set -e

DEVICE="/dev/sdb1"
PASSPHRASE="$1"
BACKUP_SRC="/data/to/backup"

# Unlock device (passphrase via stdin)
echo "$PASSPHRASE" | sudo usb-enforcer-cli unlock "$DEVICE" --passphrase-stdin

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

### Typical Use Case 5: Quick Status Checks

Check all USB devices in one command:

```bash
# Get status of all USB devices
sudo usb-enforcer-cli list --json | jq '.[] | {device: .devnode, type: .device_type, status: .status}'

# Check specific device
sudo usb-enforcer-cli status /dev/sdb1
```

## Configuration for Headless Systems

Edit `/etc/usb-enforcer/config.toml`:

```toml
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

# Restart daemon after config changes
sudo systemctl restart usb-enforcerd

# Enable at boot (already enabled by package installation)
sudo systemctl enable usb-enforcerd
```

## Advanced: Direct DBus API Usage

For power users or custom integrations, you can interact with the DBus API directly.

### Using busctl (no Python required)

List devices:
```bash
busctl call org.seravault.UsbEnforcer /org/seravault/UsbEnforcer \
  org.seravault.UsbEnforcer ListDevices
```

Get device status:
```bash
busctl call org.seravault.UsbEnforcer /org/seravault/UsbEnforcer \
  org.seravault.UsbEnforcer GetDeviceStatus s "/dev/sdb1"
```

**Note:** For unlock/encrypt operations via DBus, you must handle the secret socket communication. The CLI tool handles this for you.

### Python DBus Example

For custom Python scripts, here's a minimal unlock example:

```python
#!/usr/bin/env python3
import sys
import getpass
import pydbus
from usb_enforcer import secret_socket

devnode = sys.argv[1]
passphrase = getpass.getpass(f"Passphrase for {devnode}: ")

# Send passphrase via secret socket, get token
token = secret_socket.send_secret("unlock", devnode, passphrase)

# Call DBus method with token
bus = pydbus.SystemBus()
proxy = bus.get("org.seravault.UsbEnforcer", "/org/seravault/UsbEnforcer")
result = proxy.RequestUnlock(devnode, "", token)
print(result)
```

### Direct cryptsetup Commands (Emergency)

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

## Troubleshooting

### CLI Command Not Found

If `usb-enforcer-cli` is not found:

```bash
# Check if installed
which usb-enforcer-cli

# Should return: /usr/bin/usb-enforcer-cli

# If not, check package installation
dpkg -l | grep usb-enforcer  # Debian/Ubuntu
rpm -qa | grep usb-enforcer  # RHEL/Fedora
```

### Permission Denied

All CLI commands require root privileges via `sudo`:

```bash
# Wrong - will fail
usb-enforcer-cli list

# Correct
sudo usb-enforcer-cli list
```

### Device Not Listed

If a device doesn't appear:

```bash
# Check if daemon detected it
sudo journalctl -u usb-enforcerd -f

# Check system logs
dmesg | tail -n 50

# Verify device exists
lsblk
```

### Unlock Fails

If unlock fails with wrong passphrase:

```bash
# Check LUKS header
sudo cryptsetup luksDump /dev/sdb1

# Verify device is not already unlocked
ls /dev/mapper/

# Try manual cryptsetup
sudo cryptsetup luksOpen /dev/sdb1 test-unlock
```

## See Also

- [ADMINISTRATION.md](ADMINISTRATION.md) - Policy configuration and admin GUI
- [TESTING.md](TESTING.md) - Testing the USB enforcer
- [USB-ENFORCER.md](USB-ENFORCER.md) - Main documentation

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

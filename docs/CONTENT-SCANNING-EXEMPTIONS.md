# Content Scanning for Exempted Users

## Overview

This document explains how content scanning works for users exempted from encryption enforcement via group membership.

## Background

USB Enforcer has two main functions:
1. **Encryption Enforcement**: Force USB drives to be encrypted (LUKS2)
2. **Content Verification**: Scan files for sensitive data before writing

Users can be exempted from encryption enforcement by adding them to configured groups (e.g., `usb-exempt`). However, **content scanning still applies** to these exempted users when writing to unencrypted USB drives.

## How It Works

### Exempted Users (Can Write to Plaintext USB)

When a user in an exempted group inserts an unencrypted USB drive:

1. **Device Detection**: Daemon detects the plaintext USB device
2. **Exemption Check**: Enforcer checks if any active user is in an exempted group
3. **Classification**: Device marked as "exempt" instead of "block_rw"
4. **Mounting**:
   - If content scanning **enabled**: Device mounted writable, then overlayed with FUSE for scanning
   - If content scanning **disabled**: Device mounted writable without scanning
5. **Write Interception** (if scanning enabled):
   - All write operations intercepted by FUSE overlay
   - Files scanned for sensitive patterns before writing
   - GUI notification shows scan progress
   - Blocked files cannot be written to the USB

### Non-Exempted Users (Cannot Write to Plaintext USB)

When a non-exempted user inserts an unencrypted USB drive:

1. Device set to read-only at block level
2. Mounted as read-only
3. No content scanning needed (writes are impossible)

### Encrypted USB Drives (All Users)

When any user (exempted or not) unlocks an encrypted USB drive:

1. Device unlocked via LUKS
2. If content scanning **enabled**: Overlayed with FUSE for scanning
3. If content scanning **disabled**: Mounted normally
4. **Write Interception** (if scanning enabled):
   - All writes scanned before being allowed
   - GUI notifications shown
   - Sensitive data blocked

## Configuration

Enable content scanning in `/etc/usb-enforcer/config.toml`:

```toml
[content_scanning]
enabled = true
scan_archives = true
scan_documents = true
max_file_size_mb = 100
max_scan_time_seconds = 30
block_on_detection = true
```

Configure exempted groups:

```toml
# Users in these groups can write to unencrypted USB drives
exempted_groups = ["usb-exempt", "developers"]
```

## Implementation Details

### Code Changes (daemon.py)

1. **New Method**: `_trigger_mount_rw_with_fuse(devnode)`
   - Mounts plaintext device as writable
   - Sets up FUSE overlay for content scanning
   - Fixes ownership for user session

2. **Updated Method**: `_setup_fuse_overlay(device_path, base_mount=None)`
   - Now supports both encrypted devices (via mapper) and plaintext devices
   - `base_mount` parameter allows specifying existing mount point
   - Unmounts device, then remounts through FUSE for scanning

3. **Updated Method**: `handle_device()`
   - Detects when device is "exempt" (user in exempted group)
   - Triggers FUSE setup for writable plaintext devices
   - Skips FUSE if content scanning disabled

### Flow Diagram

```
┌─────────────────────────────┐
│ Unencrypted USB Inserted    │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│ Check User Exemption        │
└──────────┬──────────────────┘
           │
           ├─── Exempted? ────┐
           │                  │
           ▼ YES              ▼ NO
┌──────────────────┐   ┌──────────────────┐
│ Mount Writable   │   │ Set Read-Only    │
└────────┬─────────┘   │ Mount Read-Only  │
         │             └──────────────────┘
         ▼
┌──────────────────────────────┐
│ Content Scanning Enabled?    │
└────────┬─────────────────────┘
         │
         ├─── YES ────┐
         │            │
         ▼            ▼ NO
┌──────────────┐   ┌──────────────┐
│ Setup FUSE   │   │ Normal Mount │
│ Overlay      │   │ (No Scan)    │
└──────┬───────┘   └──────────────┘
       │
       ▼
┌─────────────────────────────┐
│ Intercept All Writes        │
│ - Scan for sensitive data   │
│ - Show GUI progress         │
│ - Block if detected         │
└─────────────────────────────┘
```

## Benefits

1. **Dual Protection**: Exempted users can work with unencrypted drives but still protected from data leakage
2. **Flexibility**: Organizations can allow specific users/teams to bypass encryption while maintaining content controls
3. **Consistent UX**: Same scanning experience for encrypted and unencrypted drives
4. **Defense in Depth**: Even if encryption bypassed, sensitive data still prevented from leaking

## Limitations

1. **Performance**: FUSE overlay adds slight overhead for file operations
2. **Bypass Risk**: Exempted users could potentially copy data to system drive then to USB (outside FUSE control)
3. **Pattern Limitations**: Scanning only detects known patterns (SSN, credit cards, etc.)

## Testing

To test with an exempted user:

```bash
# Add user to exemption group
sudo usermod -a -G usb-exempt username

# Insert unencrypted USB drive

# Try to write a file with sensitive data
echo "SSN: 123-45-6789" > /run/media/username/USB/test.txt

# Should see notification and file should be blocked
```

## Related Files

- [daemon.py](src/usb_enforcer/daemon.py) - Main daemon with FUSE integration
- [enforcer.py](src/usb_enforcer/encryption/enforcer.py) - Exemption checking logic
- [user_utils.py](src/usb_enforcer/encryption/user_utils.py) - Group membership functions
- [fuse_overlay.py](src/usb_enforcer/content_verification/fuse_overlay.py) - FUSE filesystem implementation
- [notifications.py](src/usb_enforcer/content_verification/notifications.py) - GUI progress windows

## See Also

- [GROUP-EXEMPTIONS.md](docs/GROUP-EXEMPTIONS.md) - Group exemption configuration
- [FUSE-OVERLAY-GUIDE.md](FUSE-OVERLAY-GUIDE.md) - Complete FUSE implementation guide
- [CONTENT-VERIFICATION-WHITEPAPER.md](docs/CONTENT-VERIFICATION-WHITEPAPER.md) - Content scanning technical details

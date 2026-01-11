# USB Enforcer Administration Guide

Complete guide for system administrators on configuring and managing USB Enforcer.

## Table of Contents
1. [Configuration File Location](#configuration-file-location)
2. [Configuration Options](#configuration-options)
3. [Service Management](#service-management)
4. [User Exemptions](#user-exemptions)
5. [Monitoring and Logs](#monitoring-and-logs)
6. [Common Administrative Tasks](#common-administrative-tasks)
7. [Troubleshooting](#troubleshooting)

---

## Configuration File Location

### Primary Configuration
The main configuration file is located at:
```
/etc/usb-enforcer/config.toml
```

### Sample Configuration
A sample configuration file with all available options is included in the package:
```
/etc/usb-enforcer/config.toml.sample
```

If the main config file doesn't exist, the daemon will use built-in defaults.

### Creating Initial Configuration
```bash
# Copy sample to active config
sudo cp /etc/usb-enforcer/config.toml.sample /etc/usb-enforcer/config.toml

# Edit as needed
sudo nano /etc/usb-enforcer/config.toml

# Restart daemon to apply changes
sudo systemctl restart usb-enforcerd.service
```

---

## Configuration Options

### Basic Enforcement Settings

#### `enforce_on_usb_only`
**Type:** Boolean  
**Default:** `true`  
**Description:** Only enforce encryption on USB devices. When `true`, devices on other buses (SATA, NVMe, etc.) are ignored.

```toml
enforce_on_usb_only = true
```

#### `allow_luks1_readonly`
**Type:** Boolean  
**Default:** `true`  
**Description:** Allow LUKS1-encrypted devices to be mounted read-only. When `false`, LUKS1 devices are completely blocked.

```toml
allow_luks1_readonly = true
```

#### `notification_enabled`
**Type:** Boolean  
**Default:** `true`  
**Description:** Enable desktop notifications for USB events. Requires the UI service to be running.

```toml
notification_enabled = true
```

---

### Mount Options

#### `default_plain_mount_opts`
**Type:** Array of strings  
**Default:** `["nodev", "nosuid", "noexec", "ro"]`  
**Description:** Mount options enforced on plaintext (unencrypted) USB devices.

```toml
default_plain_mount_opts = ["nodev", "nosuid", "noexec", "ro"]
```

**Common options:**
- `ro` - Read-only (required for enforcement)
- `nodev` - Prevent device file interpretation
- `nosuid` - Ignore setuid/setgid bits
- `noexec` - Prevent execution of binaries

#### `default_encrypted_mount_opts`
**Type:** Array of strings  
**Default:** `["nodev", "nosuid", "rw"]`  
**Description:** Mount options for LUKS2-encrypted USB devices.

```toml
default_encrypted_mount_opts = ["nodev", "nosuid", "rw"]
```

#### `require_noexec_on_plain`
**Type:** Boolean  
**Default:** `true`  
**Description:** Enforce that `noexec` is included in plain mount options for additional security.

```toml
require_noexec_on_plain = true
```

---

### Encryption Settings

#### `min_passphrase_length`
**Type:** Integer  
**Default:** `12`  
**Description:** Minimum passphrase length required when encrypting drives. Enforced by the wizard UI.

```toml
min_passphrase_length = 12
```

**Recommendations:**
- Minimum: 12 characters (default)
- Recommended: 16+ characters for high-security environments
- Maximum: No limit (LUKS2 supports very long passphrases)

#### `filesystem_type`
**Type:** String  
**Default:** `"exfat"`  
**Description:** Default filesystem type to create on encrypted drives.

```toml
filesystem_type = "exfat"
```

**Supported values:**
- `"exfat"` - Cross-platform compatibility (Windows, macOS, Linux)
- `"ext4"` - Linux-native, better performance on Linux
- `"vfat"` or `"fat32"` - Legacy compatibility, 4GB file size limit

**Requirements:**
- `exfat`: Requires `exfatprogs` package
- `ext4`: Requires `e2fsprogs` package (usually pre-installed)
- `vfat`: Requires `dosfstools` package (usually pre-installed)

#### `encryption_target_mode`
**Type:** String  
**Default:** `"whole_disk"`  
**Description:** Encryption target mode (currently only `"whole_disk"` is supported).

```toml
encryption_target_mode = "whole_disk"
```

---

### Cryptography Settings

#### KDF (Key Derivation Function)

```toml
[kdf]
type = "argon2id"
```

**Type:** String  
**Default:** `"argon2id"`  
**Description:** Key derivation function for LUKS2 encryption.

**Supported values:**
- `"argon2id"` - Recommended (memory-hard, CPU-hard, side-channel resistant)
- `"argon2i"` - Alternative (optimized for side-channel resistance)
- `"pbkdf2"` - Legacy (not recommended for new deployments)

**Note:** Argon2id provides the best balance of security and performance.

#### Cipher Configuration

```toml
[cipher]
type = "aes-xts-plain64"
key_size = 512
```

**`type`**  
**Type:** String  
**Default:** `"aes-xts-plain64"`  
**Description:** Cipher mode for LUKS2 encryption.

**Supported values:**
- `"aes-xts-plain64"` - Recommended (XTS mode with 64-bit sector numbers)
- `"aes-cbc-essiv:sha256"` - Legacy (not recommended)

**`key_size`**  
**Type:** Integer  
**Default:** `512`  
**Description:** Encryption key size in bits.

**Supported values:**
- `256` - AES-256 (XTS uses 128-bit for encryption + 128-bit for tweaking)
- `512` - AES-512 (XTS uses 256-bit for encryption + 256-bit for tweaking) - Recommended

---

### User Exemptions

#### `exempted_groups`
**Type:** Array of strings  
**Default:** `[]` (empty - no exemptions)  
**Description:** Linux groups whose members bypass USB encryption enforcement.

```toml
exempted_groups = ["usb-exempt", "developers", "sysadmin"]
```

**Use cases:**
- IT administrators who need unrestricted USB access
- Developers working with hardware devices
- Emergency response personnel
- System maintenance staff

**See:** [GROUP-EXEMPTIONS.md](GROUP-EXEMPTIONS.md) for detailed setup instructions.

---

## Service Management

### System Services

USB Enforcer consists of two services:

1. **Daemon Service** (system-wide, runs as root)
   - Unit: `usb-enforcerd.service`
   - Scope: System-wide (`/etc/systemd/system/`)
   - Manages: Device enforcement, DBus API, encryption/unlock operations

2. **UI Service** (per-user, runs as logged-in user)
   - Unit: `usb-enforcer-ui.service`
   - Scope: User session (`/usr/lib/systemd/user/`)
   - Manages: Desktop notifications, wizard launcher

### Daemon Service Commands

```bash
# Check status
sudo systemctl status usb-enforcerd.service

# Start service
sudo systemctl start usb-enforcerd.service

# Stop service
sudo systemctl stop usb-enforcerd.service

# Restart service (e.g., after config changes)
sudo systemctl restart usb-enforcerd.service

# Enable at boot
sudo systemctl enable usb-enforcerd.service

# Disable at boot
sudo systemctl disable usb-enforcerd.service

# View logs
sudo journalctl -u usb-enforcerd.service -f
```

### UI Service Commands

**Note:** Run these as the logged-in user (not with sudo):

```bash
# Check status
systemctl --user status usb-enforcer-ui.service

# Start service
systemctl --user start usb-enforcer-ui.service

# Stop service
systemctl --user stop usb-enforcer-ui.service

# Restart service
systemctl --user restart usb-enforcer-ui.service

# View logs
journalctl --user -u usb-enforcer-ui.service -f
```

### Applying Configuration Changes

After editing `/etc/usb-enforcer/config.toml`:

```bash
# Restart daemon to reload configuration
sudo systemctl restart usb-enforcerd.service

# Verify config was loaded (check logs)
sudo journalctl -u usb-enforcerd.service -n 20 --no-pager
```

---

## Monitoring and Logs

### Viewing Real-Time Logs

**Daemon logs:**
```bash
sudo journalctl -u usb-enforcerd.service -f
```

**UI logs:**
```bash
journalctl --user -u usb-enforcer-ui.service -f
```

**Combined view (requires two terminals):**
```bash
# Terminal 1
sudo journalctl -u usb-enforcerd.service -f

# Terminal 2
journalctl --user -u usb-enforcer-ui.service -f
```

### Log Filtering

**Show last 50 entries:**
```bash
sudo journalctl -u usb-enforcerd.service -n 50 --no-pager
```

**Show logs since specific time:**
```bash
sudo journalctl -u usb-enforcerd.service --since "1 hour ago"
sudo journalctl -u usb-enforcerd.service --since "2024-01-15 14:00"
```

**Show errors only:**
```bash
sudo journalctl -u usb-enforcerd.service -p err
```

**Show logs for specific device:**
```bash
sudo journalctl -u usb-enforcerd.service | grep sdb
```

### Important Log Events

**Device detection:**
```
USB device detected: /dev/sdb (plaintext)
```

**Enforcement actions:**
```
Applied ro flag to /dev/sdb1 (plaintext partition)
```

**Encryption operations:**
```
Encryption started for /dev/sdb
Encryption completed successfully for /dev/sdb
```

**Unlock operations:**
```
Unlock requested for /dev/sdb
Unlocked device mapped to /dev/mapper/usb-enforcer-XXXXX
```

**Exemptions:**
```
User bob in exempted group 'developers' - bypassing enforcement for /dev/sdb
```

---

## Common Administrative Tasks

### Task 1: Set Up User Exemptions

```bash
# 1. Create exemption group
sudo groupadd usb-exempt

# 2. Add users to group
sudo usermod -a -G usb-exempt alice
sudo usermod -a -G usb-exempt bob

# 3. Edit config
sudo nano /etc/usb-enforcer/config.toml

# 4. Add exempted_groups line
# exempted_groups = ["usb-exempt"]

# 5. Restart daemon
sudo systemctl restart usb-enforcerd.service

# 6. Verify users see exemption (after re-login)
# Check logs when they plug in a USB device
```

See [GROUP-EXEMPTIONS.md](GROUP-EXEMPTIONS.md) for details.

### Task 2: Change Minimum Passphrase Length

```bash
# Edit config
sudo nano /etc/usb-enforcer/config.toml

# Change min_passphrase_length value
# min_passphrase_length = 16

# Restart daemon
sudo systemctl restart usb-enforcerd.service
```

### Task 3: Switch Default Filesystem to ext4

```bash
# Edit config
sudo nano /etc/usb-enforcer/config.toml

# Change filesystem_type
# filesystem_type = "ext4"

# Restart daemon
sudo systemctl restart usb-enforcerd.service
```

### Task 4: Disable Enforcement Temporarily

```bash
# Stop daemon
sudo systemctl stop usb-enforcerd.service

# Devices plugged in now won't be enforced
# To re-enable:
sudo systemctl start usb-enforcerd.service
```

### Task 5: Check If User Has Exemption

```bash
# Check user's groups
groups username

# Or check if specific group exists
getent group usb-exempt
```

### Task 6: Manually Encrypt a Device (Command Line)

See [HEADLESS-USAGE.md](HEADLESS-USAGE.md) for detailed command-line encryption instructions.

---

## Troubleshooting

### Issue: Notifications Not Appearing

**Check UI service status:**
```bash
systemctl --user status usb-enforcer-ui.service
```

**Check UI logs:**
```bash
journalctl --user -u usb-enforcer-ui.service -n 50 --no-pager
```

**Common causes:**
- UI service not running (start it: `systemctl --user start usb-enforcer-ui.service`)
- `libnotify-bin` package not installed (install it: `sudo apt install libnotify-bin`)
- No notification daemon running (check desktop environment settings)

**Test notifications manually:**
```bash
notify-send "Test" "This is a test notification"
```

### Issue: Wizard Won't Open

**Test wizard manually:**
```bash
/usr/libexec/usb-enforcer-wizard
```

**Check for errors in output:**
- `ModuleNotFoundError: No module named 'gi'` - GTK dependencies missing
- Virtual environment issues - Try recreating venv

**Fix virtual environment:**
```bash
sudo rm -rf /usr/lib/usb-enforcer/.venv
sudo systemctl restart usb-enforcerd.service
```

### Issue: Device Not Being Enforced

**Check daemon logs:**
```bash
sudo journalctl -u usb-enforcerd.service -n 100 --no-pager | grep -i "sdb"
```

**Verify device is USB:**
```bash
udevadm info --query=all --name=/dev/sdb | grep ID_BUS
# Should show: ID_BUS=usb
```

**Check if user has exemption:**
```bash
groups
# Check if any groups match exempted_groups in config
```

**Check configuration:**
```bash
cat /etc/usb-enforcer/config.toml | grep enforce_on_usb_only
```

### Issue: Cannot Mount Encrypted Device

**Check if device was unlocked:**
```bash
ls -l /dev/mapper/ | grep usb-enforcer
```

**Check unlock logs:**
```bash
sudo journalctl -u usb-enforcerd.service | grep -i unlock
```

**Try manual unlock:**
```bash
/usr/libexec/usb-enforcer-helper unlock /dev/sdb
```

### Issue: Configuration Changes Not Applied

**Verify config syntax:**
```bash
# TOML syntax errors will cause config to fail loading
cat /etc/usb-enforcer/config.toml
```

**Restart daemon:**
```bash
sudo systemctl restart usb-enforcerd.service
```

**Check logs for config load errors:**
```bash
sudo journalctl -u usb-enforcerd.service -n 20 --no-pager | grep -i config
```

### Issue: Service Won't Start

**Check service status:**
```bash
sudo systemctl status usb-enforcerd.service
```

**Check for errors:**
```bash
sudo journalctl -u usb-enforcerd.service -n 50 --no-pager
```

**Common causes:**
- Python dependencies missing (reinstall package)
- Permission issues (check file ownership in `/usr/lib/usb-enforcer/`)
- Configuration syntax errors

**Verify dependencies:**
```bash
/usr/lib/usb-enforcer/.venv/bin/python3 -c "import pyudev, pydbus; print('OK')"
```

---

## Security Considerations

### Principle of Least Privilege
- Only daemon runs as root
- UI components run as user
- Secrets passed via UNIX socket (never DBus)
- Polkit enforces permission boundaries

### Exemption Best Practices
- Use exemptions sparingly
- Document who has exemptions and why
- Regularly audit exempted users
- Consider temporary exemptions for specific tasks
- Use descriptive group names (e.g., `usb-exempt-it-staff`)

### Passphrase Requirements
- Minimum 12 characters (default)
- Consider 16+ for high-security environments
- Educate users on strong passphrases
- No automatic passphrase recovery - secure backups are essential

### Monitoring Recommendations
- Review logs regularly for unusual activity
- Monitor exemption usage
- Track failed unlock attempts
- Set up log forwarding for centralized monitoring

---

## Additional Resources

- **Main Documentation:** [USB-ENFORCER.md](USB-ENFORCER.md)
- **Group Exemptions:** [GROUP-EXEMPTIONS.md](GROUP-EXEMPTIONS.md)
- **Headless Usage:** [HEADLESS-USAGE.md](HEADLESS-USAGE.md)
- **Sample Configuration:** `/etc/usb-enforcer/config.toml.sample`
- **Package Installation:** [README.md](../README.md#installing-and-running)

---

## Quick Reference

### Essential Commands

```bash
# Service management
sudo systemctl status usb-enforcerd.service
sudo systemctl restart usb-enforcerd.service
systemctl --user status usb-enforcer-ui.service

# Logs
sudo journalctl -u usb-enforcerd.service -f
journalctl --user -u usb-enforcer-ui.service -f

# Configuration
sudo nano /etc/usb-enforcer/config.toml
sudo systemctl restart usb-enforcerd.service

# Manual operations
/usr/libexec/usb-enforcer-wizard
/usr/libexec/usb-enforcer-helper unlock /dev/sdX
```

### Configuration File Template

```toml
# /etc/usb-enforcer/config.toml
enforce_on_usb_only = true
allow_luks1_readonly = true
default_plain_mount_opts = ["nodev", "nosuid", "noexec", "ro"]
default_encrypted_mount_opts = ["nodev", "nosuid", "rw"]
require_noexec_on_plain = true
min_passphrase_length = 12
encryption_target_mode = "whole_disk"
filesystem_type = "exfat"
notification_enabled = true
exempted_groups = []

[kdf]
type = "argon2id"

[cipher]
type = "aes-xts-plain64"
key_size = 512
```

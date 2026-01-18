# USB Enforcer Administration GUI

A graphical user interface for configuring USB Enforcer security policies and content scanning settings.

## Overview

The USB Enforcer Administration GUI provides an intuitive, user-friendly interface for editing the `config.toml` file. It features organized sections, inline help, validation, and direct links to documentation.

## Features

- **Intuitive Interface**: Organized into logical sections (Basic, Security, Encryption, Content Scanning, Advanced)
- **Visual Controls**: Switches, dropdowns, spin buttons, and text areas for all configuration options
- **Inline Help**: Detailed descriptions for every setting
- **Documentation Links**: One-click access to relevant documentation
- **Real-time Validation**: Prevents invalid configuration values
- **Backup Support**: Automatically creates backups before saving
- **Privilege Management**: Uses polkit for secure administrative access

## Configuration Sections

### Basic Enforcement
- USB-only enforcement toggle
- LUKS1 read-only access
- Write access with content scanning
- Desktop notifications
- Minimum passphrase length
- Group-based exemptions

### Security Settings
- Secret token TTL and limits
- Mount options for plaintext and encrypted devices
- No-execute enforcement

### Encryption Settings
- Target mode (whole disk vs. partition)
- Filesystem type (exFAT, ext4, NTFS)
- Key derivation function (KDF)
- Cipher algorithm and key size

### Content Scanning (DLP)
- Enable/disable scanning
- Enforcement scope
- Action on detection (block/warn/log)
- Scan categories (financial, pii/personal, corporate/authentication, medical)
- Performance limits
- File size and timeout settings

### Advanced Scanning
- Archive scanning (ZIP, 7z, RAR, TAR)
- Document scanning (PDF, DOCX, XLSX, PPTX)
- N-gram machine learning analysis
- Scan result caching

## Installation

### Package Installation (Recommended)

#### Debian/Ubuntu:
```bash
# Build the package
make deb-admin

# Install the package
sudo dpkg -i dist/usb-enforcer-admin_*.deb
sudo apt-get install -f  # Install any missing dependencies
```

#### Fedora/RHEL:
```bash
# Build the package
make rpm-admin

# Install the package
sudo dnf install dist/usb-enforcer-admin-*.noarch.rpm
```

### Direct Installation

```bash
# Run the installation script
sudo make admin-install

# Or directly:
sudo bash scripts/install-admin.sh
```

## Usage

### Launching the GUI

**From Application Menu:**
1. Open your application launcher
2. Search for "USB Enforcer Admin" or "USB Enforcer Configuration"
3. Click to launch

**From Command Line:**
```bash
# Using pkexec (recommended)
pkexec usb-enforcer-admin

# Or with sudo
sudo usb-enforcer-admin

# With custom config path
sudo usb-enforcer-admin --config /path/to/config.toml
```

### Making Changes

1. Navigate through the sections using the sidebar
2. Modify settings as needed
3. Click documentation links (📖) for detailed information
4. Click "Save Configuration" when done
5. Restart the daemon to apply changes:
   ```bash
   sudo systemctl restart usb-enforcerd
   ```

## Configuration File

The admin GUI edits `/etc/usb-enforcer/config.toml` by default. A backup is automatically created at `/etc/usb-enforcer/config.toml.backup` before saving.

## Dependencies

### Required:
- Python 3.8+
- python3-toml (or python3-tomli)
- GTK4
- libadwaita
- python3-gi
- polkit

### Optional:
- usb-enforcer (the main daemon package)

## Independent Usage

The admin GUI can be installed and run independently from the main USB Enforcer daemon. This is useful for:
- Remote administration
- Configuration on systems where the daemon isn't running
- Testing configuration changes before deploying
- System preparation before daemon installation

## Building from Source

### Prerequisites:
```bash
# Debian/Ubuntu
sudo apt install debhelper dh-python devscripts

# Fedora/RHEL
sudo dnf install rpm-build rpmdevtools
```

### Build Commands:
```bash
# Debian/Ubuntu
make deb-admin

# Fedora/RHEL
make rpm-admin
```

## Documentation Links

The GUI provides direct links to:
- [ADMINISTRATION.md](../docs/ADMINISTRATION.md) - Main administration guide
- [CONTENT-SCANNING-INTEGRATION.md](../docs/CONTENT-SCANNING-INTEGRATION.md) - Content scanning setup
- [FILE-TYPE-SUPPORT.md](../docs/FILE-TYPE-SUPPORT.md) - Supported file types
- [GROUP-EXEMPTIONS.md](../docs/GROUP-EXEMPTIONS.md) - Group-based exemptions
- [NOTIFICATIONS.md](../docs/NOTIFICATIONS.md) - Notification system
- [USB-ENFORCER.md](../docs/USB-ENFORCER.md) - Technical details

## Security

The admin GUI requires administrative privileges to modify the configuration file. It uses polkit for privilege escalation, ensuring proper authentication and authorization.

## Troubleshooting

### GUI won't start
- Check that all dependencies are installed
- Verify GTK4 and libadwaita are available
- Run with verbose output: `python3 -m usb_enforcer.ui.admin`

### Cannot save configuration
- Ensure you have write permissions to `/etc/usb-enforcer/`
- Check that you're running with appropriate privileges (pkexec/sudo)
- Verify the configuration directory exists

### Documentation links don't work
- Install the main usb-enforcer package for local documentation
- Or view documentation online at: https://github.com/seravault/usb-enforcer

## Support

For issues, questions, or contributions:
- GitHub: https://github.com/seravault/usb-enforcer
- Issues: https://github.com/seravault/usb-enforcer/issues

## License

GPLv3 - See LICENSE file for details

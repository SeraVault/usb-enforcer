# Building Debian Packages for USB Enforcer

This guide explains how to build Debian (.deb) packages for the USB Enforcer.

## Package Variants

Three Debian package variants are available:

### 1. Standard Package (`usb-enforcer`)
- **Size**: ~40KB
- **Python Dependencies**: Downloaded from PyPI during installation
- **Use Case**: Standard installations with internet connectivity
- **Installation**: Requires network access to download pyudev, pydbus, typing-extensions

### 2. Bundled Package (`usb-enforcer-bundled`)
- **Size**: ~200KB
- **Python Dependencies**: Bundled as wheel files in the package
- **Use Case**: Offline/airgapped environments, no internet access required
- **Installation**: All dependencies included, works without network

### 3. Admin GUI Package (`usb-enforcer-admin`)
- **Size**: ~50KB
- **Dependencies**: Separate package, can be installed independently
- **Use Case**: Graphical configuration editor for `/etc/usb-enforcer/config.toml`
- **Features**: HTML documentation viewer, live config validation

## Prerequisites

### On Debian/Ubuntu Systems
```bash
sudo apt install debhelper dh-python devscripts build-essential python3-all
```

### On Fedora/RHEL (for cross-building)
```bash
# Install dpkg tools
sudo dnf install dpkg dpkg-dev rpm-build

# Note: Building .deb on non-Debian systems may have limitations
# Recommended: Use a Debian/Ubuntu system or container
```

## Building Packages

### Build Standard Package
```bash
make deb
```

This will:
1. Create source tarball
2. Extract it with debian/ control files
3. Build the .deb package
4. Place result in `dist/` directory

### Build Bundled Package
```bash
make deb-bundled
```

This will:
1. Create source tarball
2. Download Python dependencies as wheel files
3. Extract tarball with wheels and debian-bundled/ control files
4. Build the .deb package with bundled dependencies
5. Place result in `dist/` directory

### Build Admin GUI Package
```bash
make deb-admin
```

This will:
1. Create source tarball
2. Extract with debian-admin/ control files
3. Build admin GUI package
4. Place result in `dist/` directory

### Build All Variants
```bash
make deb-all
```

This convenience target builds all three packages (standard, bundled, and admin) in one command. The output shows all built packages at the end.

Or manually:
```bash
make clean && make deb && make deb-bundled && make deb-admin
ls -lh dist/
```

## Installation

### Install Standard Package
```bash
sudo dpkg -i dist/usb-enforcer_1.0.0-1_all.deb
sudo apt-get install -f  # Install any missing dependencies
```

### Install Bundled Package
```bash
sudo dpkg -i dist/usb-enforcer-bundled_1.0.0-1_all.deb
sudo apt-get install -f  # Install any missing system dependencies
```

### Install Admin GUI Package
```bash
sudo dpkg -i dist/usb-enforcer-admin_1.0.0-1_all.deb
sudo apt-get install -f  # Install dependencies
```

## Package Contents

All main packages (standard and bundled) install the following:

### Files
- `/usr/lib/usb-enforcer/usb_enforcer/` - Python package
- `/usr/lib/usb-enforcer/.venv/` - Virtual environment (created at install time)
- `/usr/lib/usb-enforcer/wheels/` - Python wheels (bundled variant only)
- `/usr/libexec/usb-enforcerd` - System daemon
- `/usr/libexec/usb-enforcer-helper` - Helper script
- `/usr/libexec/usb-enforcer-ui` - User interface
- `/usr/libexec/usb-enforcer-wizard` - Setup wizard
- `/usr/libexec/usb-enforcer-cli` - Command-line interface
- `/usr/lib/usb-enforcer/usb-enforcer-cli.py` - CLI Python module
- `/usr/bin/usb-enforcer-cli` - CLI symlink (for PATH access)
- `/usr/bin/usb-enforcer-wizard` - Wizard symlink (for PATH access)
- `/etc/usb-enforcer/config.toml` - Configuration file
- `/usr/lib/systemd/system/usb-enforcerd.service` - System service
- `/usr/lib/systemd/user/usb-enforcer-ui.service` - User service
- `/usr/lib/udev/rules.d/49-usb-enforcer.rules` - Udev rules
- `/usr/lib/udev/rules.d/80-udisks2-usb-enforcer.rules` - Udisks2 rules
- `/etc/polkit-1/rules.d/49-usb-enforcer.rules` - Polkit rules
- `/etc/dbus-1/system.d/org.seravault.UsbEnforcer.conf` - DBus config

### Admin GUI Package Contents
- `/usr/lib/usb-enforcer/usb_enforcer/ui/admin.py` - Admin GUI application
- `/usr/share/applications/usb-enforcer-admin.desktop` - Desktop entry
- `/usr/share/doc/usb-enforcer/html/` - HTML documentation
- `/usr/share/icons/hicolor/*/apps/usb-enforcer.png` - Application icons

### Services
- System service: `usb-enforcerd.service` (enabled and started)
- User service: `usb-enforcer-ui.service` (enabled for all users)

## Uninstallation

### Remove Package (keep configuration)
```bash
sudo apt remove usb-enforcer
# or
sudo apt remove usb-enforcer-bundled
# or
sudo apt remove usb-enforcer-admin
```

### Purge Package (remove everything including configuration)
```bash
sudo apt purge usb-enforcer
# or
sudo apt purge usb-enforcer-bundled
```

This will:
- Stop and disable all services
- Remove all installed files
- Remove virtual environment
- Remove configuration files (purge only)
- Reload systemd and udev

**Note**: Purging the admin package only removes the GUI tool, not the main daemon configuration.

## Verification

### Check Package Contents
```bash
dpkg -L usb-enforcer
# or
dpkg -L usb-enforcer-bundled
```

### Check Service Status
```bash
systemctl status usb-enforcerd
systemctl --user status usb-enforcer-ui
```

### Verify Python Dependencies
```bash
/usr/lib/usb-enforcer/.venv/bin/pip list
```

## Cross-Distribution Compatibility

### Debian-based Distributions
The packages are built as `Architecture: all` (pure Python, no compiled code), making them compatible with:
- Debian 10, 11, 12+
- Ubuntu 20.04, 22.04, 24.04+
- Linux Mint
- Pop!_OS
- Elementary OS
- Other Debian derivatives

### System Requirements
- Python 3.8 or newer
- systemd
- udev
- PolicyKit
- DBus
- cryptsetup
- GTK4 with GObject Introspection (gir1.2-gtk-4.0)
- libadwaita with GObject Introspection (gir1.2-adw-1)

### Bundled Package for Airgapped Systems
The bundled variant is ideal for:
- Secure/isolated networks without internet access
- Air-gapped systems
- Environments with strict network policies
- Offline installation requirements

## Troubleshooting

### Build Failures

**Missing debhelper tools**:
```bash
sudo apt install debhelper dh-python devscripts
```

**Permission errors**:
Ensure you have write permissions to the workspace directory.

### Installation Issues

**Missing system dependencies**:
```bash
sudo apt-get install -f
```

**Service fails to start**:
Check logs:
```bash
journalctl -u usb-enforcerd -n 50
```

**Python dependencies not found** (standard package):
Ensure internet connectivity during installation, or use the bundled package.

### Package Conflicts

If you want to switch between standard and bundled:
```bash
# Remove one before installing the other
sudo apt remove usb-enforcer
sudo dpkg -i dist/usb-enforcer-bundled_1.0.0-1_all.deb
```

## Package Metadata

### Control File Fields
- **Package**: usb-enforcer or usb-enforcer-bundled
- **Version**: 1.0.0-1
- **Architecture**: all (platform-independent)
- **Section**: admin
- **Priority**: optional
- **Depends**: System packages (systemd, udev, python3, etc.)
- **Provides**: Bundled Python packages (bundled variant only)

### Maintainer Scripts
- **postinst**: Creates venv, installs Python deps, enables services
- **prerm**: Stops services before removal
- **postrm**: Cleanup on removal, purge config on purge

## Development Notes

### Modifying Package Files
Standard package control files: `debian/`
Bundled package control files: `debian-bundled/`

After modifications, rebuild:
```bash
make clean && make deb-bundled
```

### Updating Version
Edit these files:
1. `Makefile` - Update VERSION variable
2. `debian/changelog` and `debian-bundled/changelog`
3. Rebuild packages

### Testing in Clean Environment
Use Docker or VM for clean installation testing:
```bash
docker run -it --rm -v $(pwd):/workspace debian:12
cd /workspace
apt update && apt install ./dist/usb-enforcer_1.0.0-1_all.deb
```

## Additional Resources

- Debian Policy Manual: https://www.debian.org/doc/debian-policy/
- Debian New Maintainers' Guide: https://www.debian.org/doc/manuals/maint-guide/
- debhelper: https://manpages.debian.org/debhelper

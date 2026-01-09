# Building RPM Packages

This guide shows how to build RPM packages for USB Encryption Enforcer.

## Two RPM Variants

**Standard RPM** (`make rpm`):
- Small file size (~100KB)
- Downloads Python dependencies from PyPI during installation
- Requires network connection during `rpm -i`
- Best for: Development, systems with internet access

**Bundled RPM** (`make rpm-bundled`):
- Larger file size (~15MB)
- Includes all Python dependencies as wheels
- No network required during installation
- Best for: Airgapped systems, enterprise deployments, consistent versions

## Prerequisites

Install the required build tools:

```bash
# Fedora/RHEL/CentOS
sudo dnf install rpm-build rpmdevtools

# OpenSUSE
sudo zypper install rpm-build rpmdevtools
```

Set up your RPM build environment (only needed once):

```bash
rpmdev-setuptree
```

This creates the `~/rpmbuild/` directory structure.

## Building the RPM

### Quick Build - Standard RPM

Build the standard RPM (downloads deps during install):

```bash
make rpm
```

### Quick Build - Bundled RPM (Recommended for Production)

Build the bundled RPM with embedded Python dependencies:

```bash
make rpm-bundled
```

Both RPMs will be created in `~/rpmbuild/RPMS/noarch/`.

### Step-by-Step Build

#### Standard RPM
1. **Create the source tarball:**
   ```bash
   make dist
   ```
   This creates `usb-encryption-enforcer-1.0.0.tar.gz`.

2. **Build source RPM (optional):**
   ```bash
   make srpm
   ```
   Creates a source RPM in `~/rpmbuild/SRPMS/`.

3. **Build binary RPM:**
   ```bash
   make rpm
   ```
   Creates the installable RPM in `~/rpmbuild/RPMS/noarch/`.

#### Bundled RPM
1. **Download Python dependencies:**
   ```bash
   make bundle-deps
   ```
   Creates `python-deps.tar.gz` with wheel files.

2. **Build bundled RPM:**
   ```bash
   make rpm-bundled
   ```
   This automatically runs `make dist` and `make bundle-deps` first.
   
   Or do it all in one step: `make rpm-bundled`

## Installing the RPM

Once built, install the package:

```bash
sudo dnf install ~/rpmbuild/RPMS/noarch/usb-encryption-enforcer-1.0.0-1.*.noarch.rpm
```

Or using rpm directly:

```bash
sudo rpm -ivh ~/rpmbuild/RPMS/noarch/usb-encryption-enforcer-1.0.0-1.*.noarch.rpm
```

## Post-Installation

The RPM installation automatically:
- Installs Python package to `/usr/lib64/usb-encryption-enforcer/`
- Creates a Python virtual environment with dependencies
- Installs systemd services and enables the daemon
- Installs udev, polkit, and dbus rules
- Reloads udev and systemd

Start the services:

```bash
# System daemon (should already be running)
sudo systemctl status usb-encryption-enforcerd

# User notification service
systemctl --user status usb-encryption-enforcer-ui
```

## Uninstalling

Remove the package:

```bash
sudo dnf remove usb-encryption-enforcer
# or
sudo rpm -e usb-encryption-enforcer
```

The RPM removal automatically:
- Stops and disables services
- Removes the virtual environment
- Keeps configuration files (use `rpm -e --allfiles` to remove config too)

## Cross-Distribution Compatibility

### How Bundling Affects Deployment

**System Requirements** (same for both RPM variants):
- PyGObject and pycairo must come from system packages (can't be bundled)
- GTK4, libadwaita, gobject-introspection must be installed
- System tools: cryptsetup, udisks2, parted, etc.

**Bundled Python packages** (pyudev, pydbus, typing-extensions):
- Pure Python wheels work across all Linux distributions
- No compilation needed, architecture-independent
- Same bundled RPM works on Fedora, RHEL, CentOS, AlmaLinux, Rocky, SUSE

**Why some packages can't be bundled:**
- PyGObject requires libgirepository (system library binding)
- pycairo requires libcairo (system library binding)
- These MUST match the system's GTK/Cairo versions

### Testing Across Distributions

The bundled RPM should work on:
- ✅ Fedora 38+ (tested)
- ✅ RHEL 9+ / AlmaLinux 9+ / Rocky Linux 9+
- ✅ CentOS Stream 9+
- ✅ OpenSUSE Leap 15.5+ / Tumbleweed
- ⚠️  RHEL 8 / CentOS 8 (Python 3.6 may be too old)

Always test on target distributions before deploying.

## Customizing the Build

### Change Version

Edit the version in `usb-encryption-enforcer.spec` and `usb-encryption-enforcer-bundled.spec`:

```spec
Version:        1.0.0
Release:        1%{?dist}
```

Then update the `VERSION` variable in `Makefile` to match.

### Build Dependencies

The spec files automatically pull runtime dependencies. To add build-time dependencies, edit the `BuildRequires:` section in the spec files:
- Standard RPM: `rpm/usb-encryption-enforcer.spec`
- Bundled RPM: `rpm-bundled/usb-encryption-enforcer-bundled.spec`

### Installation Paths

The spec files follow standard RPM macros:
- `%{_libdir}` - `/usr/lib64` (or `/usr/lib` on 32-bit)
- `%{_libexecdir}` - `/usr/libexec`
- `%{_sysconfdir}` - `/etc`
- `%{_unitdir}` - `/usr/lib/systemd/system`
- `%{_userunitdir}` - `/usr/lib/systemd/user`

To change installation paths, modify the `%install` section in the appropriate spec file.

## Project Structure

RPM packaging files are organized in subdirectories:

```
usb-enforce-encryption/
├── rpm/
│   └── usb-encryption-enforcer.spec         # Standard RPM spec
├── rpm-bundled/
│   └── usb-encryption-enforcer-bundled.spec # Bundled RPM spec
├── debian/                                   # Debian packaging (standard)
├── debian-bundled/                           # Debian packaging (bundled)
├── Makefile                                  # Build automation
└── BUILD-RPM.md                              # This file
```

## Troubleshooting

### Build Errors

If the build fails, check:

1. All BuildRequires dependencies are installed
2. The source tarball contains all necessary files
3. The spec file paths match your file structure

View detailed build logs:
```bash
rpmbuild -bb ~/rpmbuild/SPECS/usb-encryption-enforcer.spec
```

### Runtime Issues

After installation, if services don't start:

```bash
# Check service status
sudo systemctl status usb-encryption-enforcerd
journalctl -u usb-encryption-enforcerd -f

# Verify Python dependencies in venv
/usr/lib64/usb-encryption-enforcer/.venv/bin/pip list

# Test udev rules
udevadm control --reload
udevadm test /sys/block/sdX  # replace sdX with your USB device
```

## Clean Up

Remove build artifacts:

```bash
make clean
```

This removes:
- Source tarballs
- Build directory contents
- Generated RPM packages

## Distributing

To share your RPM:

1. **Binary RPM** (ready to install):
   ```bash
   cp ~/rpmbuild/RPMS/noarch/usb-encryption-enforcer-*.noarch.rpm ./
   ```

2. **Source RPM** (for rebuilding):
   ```bash
   cp ~/rpmbuild/SRPMS/usb-encryption-enforcer-*.src.rpm ./
   ```

Users can install the binary RPM directly or rebuild from source RPM:
```bash
rpmbuild --rebuild usb-encryption-enforcer-*.src.rpm
```

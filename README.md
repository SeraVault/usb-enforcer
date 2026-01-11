# USB Enforcer

USB data loss prevention for Linux desktops: plaintext USB mass-storage devices are forced read-only, while LUKS2-encrypted devices can be unlocked and mounted writable. A Python daemon watches udev, enforces block-level `ro`, publishes DBus events, and drives a minimal notification bridge plus a GTK wizard for encryption/unlock flows.

**Available as RPM and DEB packages** for easy installation on Fedora, RHEL, Debian, Ubuntu, and derivatives. Both standard (online) and bundled (offline/airgapped) package variants are provided.

## Quick Links

- **[Installation](#installing-and-running)** - Install via RPM/DEB packages or scripts
- **[Headless/Server Usage](docs/HEADLESS-USAGE.md)** - Command-line usage without GUI
- **[Windows Access](#accessing-encrypted-drives-on-windows)** - Using encrypted drives on Windows
- **[Group Exemptions](docs/GROUP-EXEMPTIONS.md)** - Exempt specific users/groups from enforcement
- **[Building Packages](#building-packages)** - Build RPM/DEB packages
- **[Technical Details](docs/USB-ENFORCER.md)** - Architecture and design

## Supported Distributions

### Tested Distributions
This tool has been tested and is supported on:

**RPM-based:**
- Fedora 38+
- RHEL 9+ / AlmaLinux 9+ / Rocky Linux 9+
- CentOS Stream 9+
- openSUSE Leap 15.4+ / Tumbleweed

**DEB-based:**
- Ubuntu 22.04 LTS (Jammy) and newer
- Debian 12 (Bookworm) and newer
- Linux Mint 21+ (based on Ubuntu 22.04+)
- Pop!_OS 22.04+

### System Requirements
- **Python**: 3.8 or newer
- **Kernel**: Linux 5.10+ (for LUKS2 and modern udev features)
- **Systemd**: Version 245+ (for service management)
- **Desktop Environment**: 
  - **GNOME 40+** (Recommended - native GTK4/libadwaita support)
  - **Other desktops** (KDE Plasma, XFCE, etc.): Core daemon works universally, but GTK4 UI components may not match desktop theme
- **Init System**: systemd (required for service management)
- **DBus**: System and session bus support (available on all major desktops)

### Core Dependencies
- `udev` - Device management
- `udisks2` - Disk/partition operations
- `cryptsetup` 2.4.0+ - LUKS2 encryption
- `policykit-1` / `polkit` - Permission management
- `dbus` - Inter-process communication
- `python3-gi` / `PyGObject` - GTK bindings
- `gir1.2-gtk-4.0` - GTK4 introspection
- `gir1.2-adw-1` - libadwaita introspection (for wizard UI)
- `gtk4` / `libadwaita` - For encryption wizard UI

### Filesystem Support
- `exfatprogs` - For exFAT formatting (default)
- `e2fsprogs` - For ext4 formatting (optional)
- `dosfstools` - For FAT32 formatting (optional)

### Notes
- **Desktop compatibility**: Core enforcement daemon is desktop-agnostic and works on any systemd-based Linux system. GTK4 UI components (wizard, notifications) are designed for GNOME but will run on other desktops (KDE, XFCE, etc.) with visual inconsistencies.
- **Wayland/X11**: Both display servers are supported
- **Headless systems**: Core daemon works without GUI; UI components are optional. See [docs/HEADLESS-USAGE.md](docs/HEADLESS-USAGE.md) for command-line usage.
- **ARM support**: Compatible with ARM64/AArch64 systems (Raspberry Pi 4+, etc.)
- **Older distributions**: May work on older versions but are not officially tested

## How It Works
- **Udev backstop:** `deploy/udev/49-usb-enforcer.rules` marks USB partitions with filesystems read-only (excludes LUKS and dm-crypt mappers). Automount is disabled for plaintext via `deploy/udev/80-udisks2-usb-enforcer.rules`, but encrypted/mapped devices keep automount enabled.
- **Polkit policy:** `deploy/polkit/49-usb-enforcer.rules` denies `rw` mounts/remounts for plaintext USB and LUKS1 devices (ro is allowed). A permissive rule also allows udisks encryption/mount actions so the daemon/UI can operate.
- **Daemon:** `scripts/usb-enforcerd` (Python) listens to udev, classifies devices (`src/usb_enforcer/classify.py`), applies block-level `ro` for plaintext with filesystems, and logs structured events to journald. DBus API (`org.seravault.UsbEnforcer`) exposes `ListDevices`, `GetDeviceStatus`, `RequestUnlock`, and `RequestEncrypt`, plus an `Event` signal stream.
- **Secrets path:** passphrases move over a local UNIX socket (`/run/usb-enforcer.sock`); clients receive a one-time token and then call DBus with that token so secrets never traverse the system bus.
- **UI bridge:** `scripts/usb-enforcer-ui` subscribes to daemon events and shows desktop notifications. Blocked writes surface an “Encrypt drive…” action that launches the GTK wizard; encrypted inserts can trigger an unlock prompt.
- **Wizard + helper:** `scripts/usb-enforcer-wizard` (GTK4/libadwaita) lets users pick a USB device, enforce a minimum 12-char passphrase, and request encryption over DBus. The wizard includes an option to preserve existing data by copying it to a temporary location before encryption, then restoring it to the encrypted drive. The wizard currently asks the daemon to format as exfat; adjust if you want ext4. `scripts/usb-enforcer-helper` provides a simple unlock dialog.  - **Standalone access:** The wizard is also available as "USB Encryption Wizard" in your application menu, allowing you to encrypt USB devices on-demand without waiting for a notification. When launched from the menu, it shows a dropdown to select from available USB devices; when launched from a notification, the device is pre-selected.
## Configuration
- Primary config lives at `/etc/usb-enforcer/config.toml` (sample in `deploy/config.toml.sample`).
- Defaults (`src/usb_enforcer/config.py`): `enforce_on_usb_only=true`, `default_plain_mount_opts=["nodev","nosuid","noexec","ro"]`, `default_encrypted_mount_opts=["nodev","nosuid","rw"]`, `allow_luks1_readonly=true`, `min_passphrase_length=12`, `filesystem_type="exfat"` (sample config uses ext4), `kdf.type="argon2id"`, `cipher.type="aes-xts-plain64"` with a 512-bit key.
- Daemon skips block-level RO while an encryption operation is in progress to allow formatting; otherwise plaintext partitions/disks with filesystems are forced `ro`.
- **Group-based exemptions:** Set `exempted_groups = ["groupname"]` in config.toml to bypass enforcement for users in specific Linux groups. This allows administrators to exempt trusted personnel (e.g., `usb-exempt`, `developers`, `sysadmin`) from DLP restrictions while maintaining enforcement for other users. See [docs/USB-ENFORCER.md](docs/USB-ENFORCER.md#group-based-exemptions) for setup instructions.

## Installing and Running

### Installation Options

#### Option 1: Package Installation (Recommended)
Install pre-built packages for your distribution:

**RPM-based (Fedora/RHEL/CentOS/openSUSE):**
```bash
# Standard package (downloads Python deps during installation)
sudo dnf install usb-enforcer-1.0.0-1.*.noarch.rpm

# OR bundled package (offline/airgapped, no internet required)
sudo dnf install usb-enforcer-bundled-1.0.0-1.*.noarch.rpm
```

**Debian-based (Debian/Ubuntu/Mint):**
```bash
# Standard package (downloads Python deps during installation)
sudo apt install ./usb-enforcer_1.0.0-1_all.deb

# OR bundled package (offline/airgapped, no internet required)
sudo apt install ./usb-enforcer-bundled_1.0.0-1_all.deb
```

Both package types install to `/usr/lib/usb-enforcer/` with a Python virtual environment, enable systemd services automatically, and configure udev/polkit/DBus rules.

#### Option 2: Script Installation
Manual installation using install scripts:

**RHEL/Fedora/SUSE:**
```bash
sudo ./scripts/install-rhel.sh
```

**Debian/Ubuntu/Mint:**
```bash
sudo ./scripts/install-debian.sh
```

Scripts copy Python code to `/usr/lib/usb-enforcer/`, install system integration files, create a virtual environment, and enable services.

### Uninstalling

**Package uninstall:**
```bash
# RPM-based
sudo dnf remove usb-enforcer
# OR
sudo dnf remove usb-enforcer-bundled

# Debian-based
sudo apt remove usb-enforcer
# OR
sudo apt remove usb-enforcer-bundled

# Purge (removes config too)
sudo apt purge usb-enforcer
```

**Script uninstall:**
```bash
sudo ./scripts/uninstall-rhel.sh    # RHEL/Fedora/SUSE
sudo ./scripts/uninstall-debian.sh  # Debian/Ubuntu/Mint
```

### Building Packages

See [BUILD-RPM.md](BUILD-RPM.md) and [BUILD-DEB.md](BUILD-DEB.md) for detailed build instructions.

**Quick build:**
```bash
make rpm          # Build RPM (standard)
make rpm-bundled  # Build RPM (bundled)
make deb          # Build DEB (standard, requires Debian/Ubuntu)
make deb-bundled  # Build DEB (bundled, requires Debian/Ubuntu)
make clean        # Clean build artifacts
```

Built packages appear in `dist/` directory.

### Running
- **System daemon:** `usb-enforcerd.service` monitors USB devices
- **User notification bridge:** `usb-enforcer-ui.service` shows desktop notifications
- Both services are enabled automatically by installers/packages
- For ad-hoc testing: run scripts directly with `PYTHONPATH=src`

### Requirements
- **Python 3.8+** with `pyudev`, `pydbus`, `PyGObject` (see `requirements.txt`)
- **System tools:** `cryptsetup`, `udisks2`, `blockdev`, `parted`, `wipefs`, `dd`
- **Desktop:** GTK4, libadwaita, notification service (for GUI components)

## Accessing Encrypted Drives on Windows

USB drives encrypted with this tool use **LUKS2** (Linux Unified Key Setup version 2), which has limited native support on Windows. Here are your options:

### Option 1: WSL2 (Windows Subsystem for Linux) - Recommended
The most reliable way to access LUKS2 drives on Windows is through WSL2:

1. **Install WSL2** with a Linux distribution (Ubuntu recommended):
   ```powershell
   wsl --install
   ```

2. **Access the drive** from within WSL2:
   ```bash
   # List available drives
   lsblk
   
   # Unlock the LUKS2 device (e.g., /dev/sdb)
   sudo cryptsetup open /dev/sdb my_usb_drive
   
   # Mount the unlocked device
   sudo mkdir -p /mnt/usb
   sudo mount /dev/mapper/my_usb_drive /mnt/usb
   
   # Access files
   cd /mnt/usb
   
   # When done, unmount and close
   sudo umount /mnt/usb
   sudo cryptsetup close my_usb_drive
   ```

3. **Access from Windows Explorer**: WSL2 mounts are accessible at `\\wsl$\<distro-name>\mnt\usb`

### Option 2: LibreCrypt / DoxBox
[LibreCrypt](https://github.com/t-d-k/LibreCrypt) (formerly DoxBox) is an open-source Windows application with LUKS support:

- Download from the GitHub releases page
- Install and launch LibreCrypt
- Click "Linux" → "Mount LUKS volume"
- Select your USB drive and enter passphrase
- **Note**: LUKS2 support may be limited; LUKS1 has better compatibility

### Option 3: Cross-Platform Alternatives
If you frequently need Windows access, consider these alternatives to LUKS2:

- **VeraCrypt**: Cross-platform encryption (Linux, Windows, macOS) but requires reformatting drives
- **BitLocker** (Windows) + **Dislocker** (Linux): Works but requires Windows Pro/Enterprise
- **exFAT with application-layer encryption**: Use encrypted containers (VeraCrypt, 7-Zip AES) on an exFAT filesystem

### Important Notes
- **LUKS2 is primarily a Linux format**: Windows support is limited and often requires third-party tools or WSL2
- **Security trade-off**: Using cross-platform formats may have different security properties than LUKS2
- **Data portability**: If cross-platform access is required, evaluate whether LUKS2 meets your needs before encrypting drives with this tool
- **macOS support**: LUKS2 can be accessed on macOS via Homebrew's `cryptsetup` package

## Troubleshooting

### No notifications on Linux Mint
If notifications don't appear when USB drives are inserted on Linux Mint, this is due to a boot-time race condition. The quickest fix:

```bash
sudo systemctl restart usb-enforcerd.service
```

For a permanent fix, see [docs/LINUX-MINT-NOTIFICATIONS.md](docs/LINUX-MINT-NOTIFICATIONS.md).

### No notifications on Ubuntu/Debian
If notifications don't appear when USB drives are inserted:

1. **Check if the UI service is running:**
   ```bash
   systemctl --user status usb-enforcer-ui.service
   ```

2. **If service is inactive, start it manually:**
   ```bash
   systemctl --user start usb-enforcer-ui.service
   ```

3. **Check service logs:**
   ```bash
   journalctl --user -u usb-enforcer-ui.service -f
   ```

4. **Ensure it starts automatically on login:**
   ```bash
   systemctl --user enable usb-enforcer-ui.service
   systemctl --user is-enabled usb-enforcer-ui.service  # Should show "enabled"
   ```

5. **If still not working after reboot/re-login**, check notification daemon:
   ```bash
   # Verify notification service is available
   gdbus introspect --session --dest org.freedesktop.Notifications --object-path /org/freedesktop/Notifications
   ```

**Common cause:** On some distributions (especially Ubuntu), user services may not start automatically on first install. The service will start on next login, or start it manually with the command above.

### Daemon not detecting USB devices
```bash
# Check daemon status
sudo systemctl status usb-enforcerd.service

# View daemon logs
sudo journalctl -u usb-enforcerd -f

# Verify udev rules are loaded
sudo udevadm control --reload-rules
sudo udevadm trigger

# Test USB detection manually
udevadm monitor --property
# Then plug in a USB drive
```

### Permission errors
```bash
# Check if polkit rules are installed
ls -la /etc/polkit-1/rules.d/49-usb-enforcer.rules

# Reload polkit
sudo systemctl restart polkit
```

### More troubleshooting
See [docs/HEADLESS-USAGE.md](docs/HEADLESS-USAGE.md) for detailed troubleshooting steps and command-line debugging.

## More Detail
- **[docs/USB-ENFORCER.md](docs/USB-ENFORCER.md)**: Technical architecture, design goals, and enforcement policy details
- **[docs/HEADLESS-USAGE.md](docs/HEADLESS-USAGE.md)**: Complete guide for using USB Enforcer on headless/server systems without GUI
- **[docs/GROUP-EXEMPTIONS.md](docs/GROUP-EXEMPTIONS.md)**: Group-based exemption configuration

Update both this README and the docs if behavior changes (e.g., default filesystem, notification flow, or polkit rules).

## Project Structure
```
usb-enforce-encryption/
├── src/usb_enforcer/          # Python package
│   ├── classify.py            # Device classification logic
│   ├── config.py              # Configuration management
│   ├── crypto_engine.py       # LUKS encryption operations
│   ├── daemon.py              # Main daemon
│   ├── dbus_api.py            # DBus API implementation
│   └── ui/wizard.py           # GTK wizard interface
├── scripts/                   # Executable scripts
│   ├── usb-enforcerd        # System daemon
│   ├── usb-enforcer-ui      # User notification bridge
│   ├── usb-enforcer-wizard  # GTK encryption wizard
│   ├── usb-enforcer-helper  # Unlock dialog
│   ├── install-rhel.sh        # RHEL/Fedora installer
│   ├── install-debian.sh      # Debian/Ubuntu installer
│   ├── uninstall-rhel.sh      # RHEL/Fedora uninstaller
│   └── uninstall-debian.sh    # Debian/Ubuntu uninstaller
├── deploy/                    # System integration files
│   ├── config.toml.sample     # Configuration sample
│   ├── dbus/                  # DBus configuration
│   ├── polkit/                # PolicyKit rules
│   ├── systemd/               # Systemd service units
│   └── udev/                  # Udev rules
├── rpm/                       # RPM packaging (standard)
│   └── usb-enforcer.spec
├── rpm-bundled/               # RPM packaging (bundled)
│   └── usb-enforcer-bundled.spec
├── debian/                    # Debian packaging (standard)
├── debian-bundled/            # Debian packaging (bundled)
├── Makefile                   # Build automation
├── BUILD-RPM.md               # RPM build guide
├── BUILD-DEB.md               # Debian build guide
└── README.md                  # This file
```

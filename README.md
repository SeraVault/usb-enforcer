# USB Encryption Enforcer

USB data loss prevention for Linux desktops: plaintext USB mass-storage devices are forced read-only, while LUKS2-encrypted devices can be unlocked and mounted writable. A Python daemon watches udev, enforces block-level `ro`, publishes DBus events, and drives a minimal notification bridge plus a GTK wizard for encryption/unlock flows.

## How It Works
- **Udev backstop:** `deploy/udev/49-usb-encryption-enforcer.rules` marks USB partitions with filesystems read-only (excludes LUKS and dm-crypt mappers). Automount is disabled for plaintext via `deploy/udev/80-udisks2-usb-encryption-enforcer.rules`, but encrypted/mapped devices keep automount enabled.
- **Polkit policy:** `deploy/polkit/49-usb-encryption-enforcer.rules` denies `rw` mounts/remounts for plaintext USB and LUKS1 devices (ro is allowed). A permissive rule also allows udisks encryption/mount actions so the daemon/UI can operate.
- **Daemon:** `scripts/usb-encryption-enforcerd` (Python) listens to udev, classifies devices (`src/usb_enforcer/classify.py`), applies block-level `ro` for plaintext with filesystems, and logs structured events to journald. DBus API (`org.seravault.UsbEncryptionEnforcer`) exposes `ListDevices`, `GetDeviceStatus`, `RequestUnlock`, and `RequestEncrypt`, plus an `Event` signal stream.
- **Secrets path:** passphrases move over a local UNIX socket (`/run/usb-encryption-enforcer.sock`); clients receive a one-time token and then call DBus with that token so secrets never traverse the system bus.
- **UI bridge:** `scripts/usb-encryption-enforcer-ui` subscribes to daemon events and shows desktop notifications. Blocked writes surface an “Encrypt drive…” action that launches the GTK wizard; encrypted inserts can trigger an unlock prompt.
- **Wizard + helper:** `scripts/usb-encryption-enforcer-wizard` (GTK4/libadwaita) lets users pick a USB device, enforce a minimum 12-char passphrase, and request encryption over DBus. The wizard includes an option to preserve existing data by copying it to a temporary location before encryption, then restoring it to the encrypted drive. The wizard currently asks the daemon to format as exfat; adjust if you want ext4. `scripts/usb-encryption-enforcer-helper` provides a simple unlock dialog.

## Configuration
- Primary config lives at `/etc/usb-encryption-enforcer/config.toml` (sample in `deploy/config.toml.sample`).
- Defaults (`src/usb_enforcer/config.py`): `enforce_on_usb_only=true`, `default_plain_mount_opts=["nodev","nosuid","noexec","ro"]`, `default_encrypted_mount_opts=["nodev","nosuid","rw"]`, `allow_luks1_readonly=true`, `min_passphrase_length=12`, `filesystem_type="exfat"` (sample config uses ext4), `kdf.type="argon2id"`, `cipher.type="aes-xts-plain64"` with a 512-bit key.
- Daemon skips block-level RO while an encryption operation is in progress to allow formatting; otherwise plaintext partitions/disks with filesystems are forced `ro`.

## Installing and Running
- RHEL/Fedora/SUSE: run `scripts/install-rhel.sh` as root to copy Python bits to `/usr/lib/usb-encryption-enforcer`, install udev/polkit/dbus/systemd files, create a venv, and enable the services.
- Debian/Ubuntu/Mint: run `scripts/install-debian.sh` as root; it checks GTK/pygobject/udisks/notify deps before installing the same artifacts and enabling services.
- Uninstallers are available for both families (`scripts/uninstall-rhel.sh`, `scripts/uninstall-debian.sh`) and remove services, policies, and the installed venv (config removal is optional).
- Services: `usb-encryption-enforcerd.service` (system) runs the daemon; `usb-encryption-enforcer-ui.service` (user) runs the notification bridge. The installers enable both; for ad-hoc testing you can run the scripts directly from the repo with `PYTHONPATH=src`.
- Requirements: Python 3 with `pyudev`, `pydbus`, `PyGObject` (see `requirements.txt`), plus system tools `cryptsetup`, `udisks2`, `blockdev`, `parted`, `wipefs`, `dd`, and a desktop notification service.

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

## More Detail
The legacy design document lives at `docs/usb-encryption-enforcer.md` and outlines goals, UX, and policy rationale. Update both this README and the doc if behavior changes (e.g., default filesystem, notification flow, or polkit rules).

# USB Encryption Enforcer

USB data loss prevention for Linux desktops: plaintext USB mass-storage devices are forced read-only, while LUKS2-encrypted devices can be unlocked and mounted writable. A Python daemon watches udev, enforces block-level `ro`, publishes DBus events, and drives a minimal notification bridge plus a GTK wizard for encryption/unlock flows.

## How It Works
- **Udev backstop:** `deploy/udev/49-usb-encryption-enforcer.rules` marks USB partitions with filesystems read-only (excludes LUKS and dm-crypt mappers). Automount is disabled for plaintext via `deploy/udev/80-udisks2-usb-encryption-enforcer.rules`, but encrypted/mapped devices keep automount enabled.
- **Polkit policy:** `deploy/polkit/49-usb-encryption-enforcer.rules` denies `rw` mounts/remounts for plaintext USB and LUKS1 devices (ro is allowed). A permissive rule also allows udisks encryption/mount actions so the daemon/UI can operate.
- **Daemon:** `scripts/usb-encryption-enforcerd` (Python) listens to udev, classifies devices (`src/usb_enforcer/classify.py`), applies block-level `ro` for plaintext with filesystems, and logs structured events to journald. DBus API (`org.seravault.UsbEncryptionEnforcer`) exposes `ListDevices`, `GetDeviceStatus`, `RequestUnlock`, and `RequestEncrypt`, plus an `Event` signal stream.
- **UI bridge:** `scripts/usb-encryption-enforcer-ui` subscribes to daemon events and shows desktop notifications. Blocked writes surface an “Encrypt drive…” action that launches the GTK wizard; encrypted inserts can trigger an unlock prompt.
- **Wizard + helper:** `scripts/usb-encryption-enforcer-wizard` (GTK4/libadwaita) lets users pick a USB device, enforce a minimum 12-char passphrase, and request encryption over DBus. The wizard currently asks the daemon to format as exfat; adjust if you want ext4. `scripts/usb-encryption-enforcer-helper` provides a simple unlock dialog.

## Configuration
- Primary config lives at `/etc/usb-encryption-enforcer/config.toml` (sample in `deploy/config.toml.sample`).
- Defaults (`src/usb_enforcer/config.py`): `enforce_on_usb_only=true`, `default_plain_mount_opts=["nodev","nosuid","noexec","ro"]`, `default_encrypted_mount_opts=["nodev","nosuid","rw"]`, `allow_luks1_readonly=true`, `min_passphrase_length=12`, `filesystem_type="exfat"` (sample config uses ext4), `kdf.type="argon2id"`, `cipher.type="aes-xts-plain64"` with a 512-bit key.
- Daemon skips block-level RO while an encryption operation is in progress to allow formatting; otherwise plaintext partitions/disks with filesystems are forced `ro`.

## Installing and Running
- RHEL/Fedora-style systems: run `scripts/install-rhel.sh` as root to copy Python bits to `/usr/lib/usb-encryption-enforcer`, install udev/polkit/dbus/systemd files, create a venv, and enable the services.
- Services: `usb-encryption-enforcerd.service` (system) runs the daemon; `usb-encryption-enforcer-ui.service` (user) runs the notification bridge. The installer enables both; for ad-hoc testing you can run the scripts directly from the repo with `PYTHONPATH=src`.
- Requirements: Python 3 with `pyudev`, `pydbus`, `PyGObject` (see `requirements.txt`), plus system tools `cryptsetup`, `udisks2`, `blockdev`, `parted`, `wipefs`, `dd`, and a desktop notification service.

## More Detail
The legacy design document lives at `docs/usb-encryption-enforcer.md` and outlines goals, UX, and policy rationale. Update both this README and the doc if behavior changes (e.g., default filesystem, notification flow, or polkit rules).

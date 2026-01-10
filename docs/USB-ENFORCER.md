# USB Encryption Enforcement (DLP: Read-Only Plaintext, Write-Only Encrypted)

## 0) Summary
Endpoint DLP control for Linux desktops: USB mass-storage devices mount read-only when unencrypted and writable only when protected with LUKS2. Plaintext devices are forced block-level `ro` and cannot be remounted `rw`; encrypted media can be unlocked and mounted `rw`. Desktop notifications guide users to unlock or encrypt devices through a wizard. All decisions are audited to journald. Stack: udisks2 + polkit (policy), udev backstop, systemd services (root + user session), DBus API, notifications/GTK wizard (desktop-agnostic).

## 1) Goals and Non-Goals
- Enforce: plaintext USB mounts read-only; writes/remount to `rw` blocked; LUKS2 devices can be unlocked and mounted `rw`.
- Desktop UX: notifications for plaintext/encrypted inserts; actions to unlock or run an encryption wizard that formats to LUKS2 and mounts writable.
- Audit: journald logging of inserts, classification, policy decisions, blocked attempts, unlock/encrypt actions.
- Reliability: handle multiple partitions; ignore non-storage USB.
- Non-goals: cross-platform; protection against malicious root (root can override unless system lockdown is added).

## 2) Supported Platforms
- Linux desktops with udisks2 + systemd: Ubuntu 22.04+/24.04+, Debian 12+, RHEL 9+, Fedora 39+.
- File managers that use udisks (GNOME Files, etc.). Plaintext USB devices don't auto-mount but can be manually mounted with one click.

## 3) Definitions
- USB mass storage: block devices with `ID_BUS=usb` and `ID_TYPE=disk` (and their partitions).
- Plaintext device: lacks LUKS header (`ID_FS_TYPE!=crypto_LUKS`).
- Encrypted device: LUKS2 (`crypto_LUKS` and `cryptsetup luksDump` reports LUKS2).
- Compliant writable device: decrypted `/dev/mapper/*` created from LUKS2 and mounted with permitted `rw` options.

## 4) Functional Requirements
- Mount behavior:
  - USB plaintext → no auto-mount; manual mount allowed (read-only); force block-level `ro`.
  - LUKS2 devices → auto-mount after unlock; `rw` mounts allowed with policy options.
  - LUKS1/non-LUKS2 → no auto-mount; manual mount read-only (configurable to block).
  - Each partition evaluated independently.
- Remount protection: deny `ro`→`rw` on plaintext USB (udisks/polkit policy and block-level `ro` backstop).
- Notifications:
  - Plaintext: "USB detected - read-only access available. Writing requires encryption." Actions: Mount, Encrypt…, Learn more.
  - Encrypted: “Encrypted USB detected. Unlock to enable access.” Action: Unlock…
- Encryption wizard:
  - Lists USB targets; shows model/size/partitions.
  - Confirms data loss; enforces passphrase policy (default min 12 chars).
  - Creates LUKS2 (argon2id, AES-XTS 512-bit), opens mapper, builds filesystem (default ext4; optional exfat), mounts `rw`, optionally auto-opens in file manager.
- CLI/desktop coverage: applies to auto-mount and CLI `mount`/`udisksctl` attempts.
- Logging: structured journald entries for insert, classification, mount decision, blocked actions, wizard start/complete/fail, unlock success/fail (no secrets).

## 5) Configuration (/etc/usb-enforcer/config.toml)
- `enforce_on_usb_only` (bool, default true)
- `allow_luks1_readonly` (bool, default true; if false, block mounts)
- `default_plain_mount_opts` (e.g., `nodev,nosuid,noexec,ro`)
- `default_encrypted_mount_opts` (e.g., `nodev,nosuid,rw[,noexec]`)
- `require_noexec_on_plain` (bool)
- `min_passphrase_length` (int, default 12)
- `encryption_target_mode` (`whole_disk`|`single_partition`, default whole_disk)
- `filesystem_type` (`ext4`|`exfat`, default ext4)
- `notification_enabled` (bool)
- `exempted_groups` (list of strings, default empty): Linux group names whose members bypass all USB encryption enforcement. Users in any of these groups will have full read-write access to USB devices without encryption requirements. This allows administrators to exempt specific users (e.g., developers, sysadmins, or trusted personnel) from DLP restrictions while maintaining enforcement for all other users.
- `kdf` params (argon2id tunables) and `cipher` policy (AES-XTS 512-bit)

### Group-Based Exemptions
The `exempted_groups` configuration allows administrators to create per-user enforcement exemptions based on Linux group membership. When any logged-in user is a member of a group listed in `exempted_groups`, USB encryption enforcement is completely bypassed for all users on that system session.

**Use cases:**
- IT administrators who need unrestricted USB access for system maintenance
- Developers requiring frequent data transfers during testing
- Trusted personnel with approved business needs for plaintext USB access
- Emergency/temporary exemptions for specific projects

**Configuration example:**
```toml
# Create a group and add users who should bypass enforcement
exempted_groups = ["usb-exempt", "developers", "sysadmin"]
```

**Setup instructions:**
1. Create the exemption group: `sudo groupadd usb-exempt`
2. Add users to the group: `sudo usermod -aG usb-exempt username`
3. Update config.toml with the group name(s)
4. Restart the daemon: `sudo systemctl restart usb-enforcerd`
5. User must log out and back in for group membership to take effect

**Security considerations:**
- Audit group membership regularly
- Log all exempted access events with the user and group identified
- Consider using time-limited group memberships for temporary exemptions
- Group exemptions apply system-wide when those users are logged in

## 6) Enforcement Architecture
- **EA-1: udisks2 automount control + polkit (primary)**
  - Udisks2 udev rule `80-udisks2-usb-enforcer.rules`: disables auto-mount for plaintext USB (UDISKS_AUTO=0).
  - Polkit JS rule `49-usb-enforcer.rules`:
    - Scope to devices with `ID_BUS=usb`.
    - Allow mount for plaintext only if `ro` present in options.
    - Deny mount/remount `rw` for plaintext.
    - Allow `rw` mount for decrypted LUKS2 mappers.
    - Optional deny/ro-only for LUKS1 per config.
- **EA-2: udev backstop (block-level RO)**
  - Udev rule marks plaintext USB block devices read-only via `/sys/block/<dev>/ro` using helper.
  - Exclude decrypted `/dev/mapper/*` mappers from RO.
- **EA-3: systemd orchestration**
  - Root service `usb-enforcerd` watches udev, applies block-level RO, logs decisions, exposes DBus.
  - User session service/extension listens to daemon signals, shows notifications, launches wizard/unlock.

## 7) Components
- **C-1 Root daemon: usb-enforcerd**
  - Language: Python (pyudev + pydbus) or Go.
  - Functions:
    - Listen for add/change/remove udev events; classify devices (USB? plain? LUKS1? LUKS2? mapper?).
    - Enforce block-level RO for plaintext per config.
    - Publish journald logs with structured fields.
    - Expose DBus API:
      - `list_devices()`: returns device list with status (plain_ro, luks2_locked, luks2_unlocked_rw, blocked).
      - `get_device_status(devnode)`
      - `request_encrypt(devnode, options)`
      - `request_unlock(devnode)`
      - `subscribe_events()` signal stream (insert, classify, enforcement, wizard state).
- **C-2 Polkit rules**
  - File: `/etc/polkit-1/rules.d/49-usb-enforcer.rules`.
  - Enforce mount policy described in EA-1; log denials via `polkit.log`.
- **C-3 Desktop UI (systemd --user + libnotify/GTK4)**
  - User service listens on daemon DBus signals.
  - Shows notifications via `org.freedesktop.Notifications` with action buttons wired to daemon calls.
  - GTK4/libadwaita app `usb-enforcer-ui`:
    - Device picker (USB only).
    - Encryption wizard (confirmation, passphrase entry + strength meter/show toggle, progress).
    - Unlock prompt (or defer to udisks unlock dialog).
  - Alternate Shell extension acceptable; path above is the default.
- **C-4 Encryption engine**
  - Uses `cryptsetup` CLI (root daemon) with policy parameters:
    - LUKS2, argon2id, AES-XTS 512-bit.
    - Wipe/format target per `encryption_target_mode`.
    - Create filesystem (ext4 default; exfat optional).
    - Mount via udisks or direct `mount` with `default_encrypted_mount_opts`.
  - Emits progress events (percent, stage) to DBus for UI.

## 8) UX Flows
- **Plaintext insert (read-only)**:
  1. Udev event → daemon classifies plaintext → sets block RO, logs.
  2. Polkit allows only `ro` mount (auto-mount if desktop does).
  3. User sees notification: title “USB mounted read-only”; body “Writing to removable media requires encryption.” Actions: Encrypt…, Learn more.
  4. Write attempts fail with `EBUSY`/`EROFS`; optional notification re-shown.
- **Encrypted insert (unlock to write)**:
  1. Udev event → daemon classifies LUKS2; logs.
  2. Notification: “Encrypted USB detected. Unlock to enable access.” Action: Unlock…
  3. On unlock: daemon runs `cryptsetup open`; polkit permits; mount `rw` with policy opts; success notification; optional auto-open.
- **Encryption wizard**:
  1. User triggers Encrypt… action or runs UI directly.
  2. UI lists USB devices; user selects target; warned about data loss; confirms.
  3. Passphrase entry with policy enforcement; strength meter optional; confirm/passphrase visibility toggle.
  4. Daemon wipes/creates LUKS2, opens mapper, formats filesystem, mounts `rw`, sends progress/events.
  5. On success: notification and optional auto-open mount.
  6. On failure/cancel: notification with error and log reference ID.

## 9) Policy Details
- Mount options:
  - Plaintext default: `nodev,nosuid,noexec,ro`; `noexec` enforced if `require_noexec_on_plain`.
  - Encrypted default: `nodev,nosuid,rw` (optionally `noexec`).
- LUKS1 handling: default `ro` only; configurable to block mount/auto-mount entirely.
- Remount attempts:
  - Polkit denies udisks `org.freedesktop.udisks2.filesystem-modify` for `ro`→`rw` on plaintext.
  - Block-level `ro` ensures fallback even if polkit bypassed.
- Non-storage USB (ID_TYPE!=disk) ignored.

## 10) Logging and Audit (journald)
- Structured fields (examples): `USB_EE_EVENT=insert|classify|enforce|unlock|encrypt|error`, `DEVNODE=/dev/sdX`, `DEVTYPE=disk|part|mapper`, `BUS=usb`, `SERIAL=...`, `CLASSIFICATION=plaintext|luks1|luks2_locked|luks2_unlocked`, `ACTION=mount_ro|mount_rw|block_rw|remount_denied|encrypt_start|encrypt_done|encrypt_fail|unlock_start|unlock_done|unlock_fail`, `RESULT=allow|deny|fail`, `POLICY_SOURCE=polkit|udev|daemon`.
- No secrets logged; passphrases never written; include reference IDs for errors to correlate UI messages with logs.

## 11) Security Requirements
- Crypto: LUKS2, argon2id KDF, AES-XTS 512-bit; enforce minimum KDF params from config.
- Secrets handling: passphrases only in-memory; no logging; clear buffers after use.
- Least privilege: UI unprivileged; privileged operations through daemon + polkit. Root still able to override (out of scope).

## 12) Edge Cases and Reliability
- Multiple partitions: each evaluated; mixed plain/LUKS handled per-partition.
- Mapper exclusion: do not mark `/dev/mapper/*` read-only; identify parent via `DM_UUID`/`DM_NAME`.
- Device removal mid-operation: wizard handles abort; ensures mapper closed and partial mounts unmounted.
- Filesystem type detection: fallback to read-only if unknown FS on plaintext.
- Config reload: daemon reloads on SIGHUP or via DBus method; applies new policy to subsequent events.

## 13) Deployment and Packaging
- Install daemon binary/script to `/usr/libexec/usb-enforcerd` with systemd service unit.
- Install polkit rule to `/etc/polkit-1/rules.d/49-usb-enforcer.rules`.
- Install udev rule to `/etc/udev/rules.d/49-usb-enforcer.rules`.
- Install DBus policy `/etc/dbus-1/system.d/org.seravault.UsbEnforcer.conf` so the daemon can own the system bus name.
- Install user service (`~/.config/systemd/user/usb-enforcer-ui.service`) and GTK app/desktop entry for wizard.
- If enabling the user notification bridge via `/etc/systemd/user/default.target.wants`, user sessions pick it up on next login; to start immediately for the current user run: `systemctl --user daemon-reload && systemctl --user enable --now usb-enforcer-ui`.
- Wizard: `usb-enforcer-wizard` (GTK4/libadwaita) connects to the daemon over DBus for encrypt/unlock flows. Requires PyGObject and system GTK/libadwaita packages.
- Provide man page or `--help` for CLI/Wizard; ship local help page for “Learn more”.

### System package requirements for the GTK wizard (examples)
- RHEL/Fedora: `./`
- Debian/Ubuntu: `apt-get install python3-dev python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 libcairo2-dev libgirepository1.0-dev pkg-config meson`
- After installing system packages: `. .venv/bin/activate && pip install -r requirements.txt`

## 14) Testing and Validation
- Unit: device classification, config parsing, DBus API behaviors.
- Integration (VM): insert plaintext USB → mounts `ro`, write fails, notification present; remount attempt denied; journald entries recorded.
- Encrypted flow: LUKS2 insert → unlock → `rw` mount; audit entries; notification.
- LUKS1 flow: verify `ro` (or blocked) per config.
- Regression: ensure non-USB disks unaffected; ensure `/dev/mapper` not forced `ro`.
- UX: notifications appear; wizard encrypts and remounts writable; error handling messages show reference IDs.

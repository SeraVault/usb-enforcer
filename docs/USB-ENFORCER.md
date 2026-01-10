# USB Enforcer - Technical Architecture

## 0) Summary
USB Enforcer provides endpoint DLP (Data Loss Prevention) control for Linux systems. USB mass-storage devices mount read-only when unencrypted and writable only when protected with LUKS2 encryption. Plaintext devices are forced block-level `ro` and cannot be remounted `rw`; encrypted media can be unlocked and mounted `rw`. Desktop notifications guide users to unlock or encrypt devices through a GTK wizard. All decisions are audited to journald.

**Current Implementation**: Python-based daemon with udev monitoring, DBus API, polkit enforcement, optional GTK4/libadwaita UI. Available as RPM and DEB packages for all major Linux distributions. Supports both desktop and headless deployments.

**Technology Stack**: udisks2 + polkit (policy enforcement), udev (device detection + backstop), systemd services (root daemon + optional user session UI), DBus API (command/control), PyGObject + GTK4/libadwaita (optional desktop notifications and wizard).

## 1) Goals and Non-Goals
- Enforce: plaintext USB mounts read-only; writes/remount to `rw` blocked; LUKS2 devices can be unlocked and mounted `rw`.
- Desktop UX: notifications for plaintext/encrypted inserts; actions to unlock or run an encryption wizard that formats to LUKS2 and mounts writable.
- Audit: journald logging of inserts, classification, policy decisions, blocked attempts, unlock/encrypt actions.
- Reliability: handle multiple partitions; ignore non-storage USB.
- Non-goals: cross-platform; protection against malicious root (root can override unless system lockdown is added).

## 2) Supported Platforms

### Current Package Support
- **RPM-based**: Fedora 38+, RHEL 9+, AlmaLinux 9+, Rocky Linux 9+, CentOS Stream 9+, openSUSE Leap 15.4+/Tumbleweed
- **DEB-based**: Ubuntu 22.04 LTS+, Debian 12+, Linux Mint 21+, Pop!_OS 22.04+
- **Architecture**: x86_64, ARM64/AArch64 (Raspberry Pi 4+, etc.)
- **Deployment**: Desktop systems with GUI (GNOME, KDE, XFCE, etc.) and headless/server systems

### System Requirements
- Linux kernel 5.10+ (for LUKS2 and modern udev features)
- systemd 245+ (for service management)
- Python 3.8 or newer
- udisks2, cryptsetup 2.4.0+, polkit, dbus

### Desktop Integration
- File managers that use udisks (GNOME Files, Dolphin, Thunar, etc.) respect enforcement
- Plaintext USB devices don't auto-mount but can be manually mounted read-only with one click
- GTK4 wizard and notifications designed for GNOME but work on all desktops (with visual theme differences)
- Headless systems: Core daemon and DBus API work without any GUI components (see [HEADLESS-USAGE.md](HEADLESS-USAGE.md))

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
- `filesystem_type` (`exfat`|`ext4`|`vfat`, default exfat)
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
  - **Language**: Python 3.8+ (implemented with pyudev + pydbus)
  - **Location**: `/usr/lib/usb-enforcer/venv/` (virtualenv) with wrapper script in `/usr/sbin/usb-enforcerd`
  - **Service**: `usb-enforcerd.service` (systemd system service)
  - **Functions**:
    - Listen for add/change/remove udev events; classify devices (USB? plain? LUKS1? LUKS2? mapper?).
    - Enforce block-level RO for plaintext per config.
    - Publish journald logs with structured fields.
    - Expose DBus API (`org.seravault.UsbEnforcer` on system bus):
      - `ListDevices()`: returns array of device dictionaries with status, type, filesystem info.
      - `GetDeviceStatus(devnode)`: returns dictionary with detailed device information.
      - `RequestUnlock(devnode, mapper_name, token)`: unlocks LUKS2 device using passphrase token from secret socket.
      - `RequestEncrypt(devnode, mapper_name, token, fs_type, label)`: encrypts device using passphrase token from secret socket.
      - `Event` signal: emits structured events for device state changes (insert, remove, classify, mount, unlock, encrypt).
    - **Secret Socket** (`/run/usb-enforcer.sock`): UNIX domain socket for secure passphrase transmission.
      - Clients send passphrase over socket, receive one-time token.
      - Token is then passed via DBus methods (passphrases never traverse DBus).
      - Socket only accessible by root; permissions enforced by filesystem.
      - Tokens expire after single use or timeout.
      - `subscribe_events()` signal stream (insert, classify, enforcement, wizard state).
- **C-2 Polkit rules**
  - File: `/etc/polkit-1/rules.d/49-usb-enforcer.rules`.
  - Enforce mount policy described in EA-1; log denials via `polkit.log`.
- **C-3 Desktop UI (systemd --user + libnotify/GTK4)**
  - User service listens on daemon DBus signals.
  - Shows notifications via `org.freedesktop.Notifications` with action buttons wired to daemon calls.
  - GTK4/libadwaita app `usb-enforcer-wizard`:
    - Device picker (USB only) with model/size information.
    - Encryption wizard with data preservation option (backs up existing data, encrypts device, then restores data).
    - Passphrase entry with visibility toggle and minimum length enforcement (default 12 chars).
    - Real-time progress display during encryption/formatting.
  - Helper app `usb-enforcer-helper`: Simple GTK4 unlock dialog for encrypted devices.
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
  1. User triggers Encrypt… action from notification or runs `usb-enforcer-wizard` directly.
  2. UI lists USB devices with model, serial, size, and partition information; user selects target.
  3. **Data preservation option**: Checkbox to "Preserve existing data" - backs up data to temporary location before encryption, then restores after.
  4. User warned about data loss (if not preserving); confirms operation.
  5. Passphrase entry with visibility toggle, double-entry confirmation, and minimum length enforcement (configurable, default 12 chars).
  6. Daemon performs encryption workflow:
     - If preserving data: mount device, copy data to `/tmp/usb-enforcer-backup-*`, unmount
     - Wipe device (optional secure wipe)
     - Create LUKS2 container with argon2id KDF and AES-XTS 512-bit cipher
     - Open LUKS2 mapper
     - Format filesystem (exfat default, configurable to ext4/vfat)
     - Mount encrypted device read-write
     - If preserving data: restore files from backup, clean up temp directory
  7. Progress events sent via DBus; UI shows real-time progress bar and status messages.
  8. On success: notification with mount point; device ready to use with full read-write access.
  9. On failure/cancel: notification with error message; journald log entry with details.

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
- Structured fields (examples): `USB_EE_EVENT=insert|classify|enforce|unlock|encrypt|error`, `DEVNODE=/dev/sdX`, `DEVTYPE=disk|part|mapper`, `BUS=usb`, `SERIAL=...`, `CLASSIFICATION=plaintext|luks1|luks2_locked|luks2_unlocked`, `ACTION=mount_ro|mount_rw|block_rw|remount_denied|encrypt_start|encrypt_done|encrypt_fail|unlock_start|unlock_done|unlock_fail`, `RESULT=allow|deny|fail`, `POLICY_SOURCE=polkit|udev|daemon`, `USER=<username>` (for exemption tracking), `EXEMPTED_BY_GROUP=<groupname>` (when bypass is active).
- No secrets logged; passphrases never written to logs or files; include reference IDs for errors to correlate UI messages with logs.
- Group exemptions: when enforcement is bypassed due to group membership, log entries include user identity and exempting group name for audit trail.

## 11) Security Requirements
- **Cryptography**: LUKS2 with argon2id KDF and AES-XTS 512-bit cipher; enforce minimum KDF parameters from configuration.
- **Secrets handling**: 
  - Passphrases transmitted via UNIX domain socket (`/run/usb-enforcer.sock`), never via DBus.
  - Passphrases only kept in-memory; never written to disk or logs.
  - Memory buffers cleared after use; tokens expire after single use.
  - Socket permissions restrict access to root only.
- **Privilege separation**: 
  - UI components run unprivileged (user context).
  - Privileged operations (cryptsetup, blockdev) only through daemon + polkit.
  - DBus policy restricts API access to authorized processes.
- **Group exemptions**: 
  - Configured in `/etc/usb-enforcer/config.toml` with `exempted_groups` list.
  - All exempted access logged with user and group information.
  - Administrators should audit group membership regularly.
  - See [GROUP-EXEMPTIONS.md](GROUP-EXEMPTIONS.md) for setup and security considerations.
- **Limitations**: Root users can still override enforcement (system-level lockdown out of scope). Physical access to hardware allows bypass via external boot media.

## 12) Edge Cases and Reliability
- Multiple partitions: each evaluated; mixed plain/LUKS handled per-partition.
- Mapper exclusion: do not mark `/dev/mapper/*` read-only; identify parent via `DM_UUID`/`DM_NAME`.
- Device removal mid-operation: wizard handles abort; ensures mapper closed and partial mounts unmounted.
- Filesystem type detection: fallback to read-only if unknown FS on plaintext.
- Config reload: daemon reloads on SIGHUP or via DBus method; applies new policy to subsequent events.

## 13) Deployment and Packaging

### Current Package Structure
USB Enforcer is distributed as native RPM and DEB packages in two variants:
- **Standard packages**: `usb-enforcer` (downloads Python dependencies during installation)
- **Bundled packages**: `usb-enforcer-bundled` (includes all dependencies for offline/airgapped systems)

### Installation Layout
- **Daemon**: `/usr/lib/usb-enforcer/` (Python package + virtualenv)
- **Scripts**: `/usr/sbin/{usb-enforcerd,usb-enforcer-ui,usb-enforcer-wizard,usb-enforcer-helper}`
- **Configuration**: `/etc/usb-enforcer/config.toml` (user-editable)
- **Polkit rules**: `/etc/polkit-1/rules.d/49-usb-enforcer.rules`
- **Udev rules**: `/etc/udev/rules.d/{49-usb-enforcer.rules,80-udisks2-usb-enforcer.rules}`
- **DBus policy**: `/etc/dbus-1/system.d/org.seravault.UsbEnforcer.conf`
- **Systemd services**:
  - System: `/etc/systemd/system/usb-enforcerd.service` (daemon)
  - User: `/etc/systemd/user/usb-enforcer-ui.service` (optional desktop notifications/UI)

### Package Installation
```bash
# RPM-based systems
sudo dnf install usb-enforcer-1.0.0-1.*.noarch.rpm
# OR bundled version
sudo dnf install usb-enforcer-bundled-1.0.0-1.*.noarch.rpm

# DEB-based systems
sudo apt install ./usb-enforcer_1.0.0-1_all.deb
# OR bundled version
sudo apt install ./usb-enforcer-bundled_1.0.0-1_all.deb
```

### Building Packages
See [BUILD-RPM.md](../BUILD-RPM.md) and [BUILD-DEB.md](../BUILD-DEB.md) for complete build instructions.

```bash
make rpm          # Build standard RPM
make rpm-bundled  # Build bundled RPM (offline)
make deb          # Build standard DEB (requires Debian/Ubuntu)
make deb-bundled  # Build bundled DEB (offline)
```

### Service Management
Both system and user services are enabled automatically by package installers:

```bash
# Check daemon status
sudo systemctl status usb-enforcerd

# Check user UI service (desktop only)
systemctl --user status usb-enforcer-ui

# Manual enable/restart
sudo systemctl enable --now usb-enforcerd
systemctl --user enable --now usb-enforcer-ui

# View logs
sudo journalctl -u usb-enforcerd -f
journalctl --user -u usb-enforcer-ui -f
```

### Headless/Server Deployment
For systems without GUI, install the package normally - the daemon works without UI components:
- System daemon (`usb-enforcerd`) runs and enforces policies
- User UI service won't start (no display server)
- All operations accessible via DBus API from command-line
- See [HEADLESS-USAGE.md](HEADLESS-USAGE.md) for command-line usage examples

### System package requirements for the GTK wizard (examples)
- RHEL/Fedora: `./`
- Debian/Ubuntu: `apt-get install python3-dev python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 libcairo2-dev libgirepository1.0-dev pkg-config meson`
- After installing system packages: `. .venv/bin/activate && pip install -r requirements.txt`

## 14) Testing and Validation

### Unit Testing
- Device classification logic (plaintext, LUKS1, LUKS2, mapper identification)
- Configuration parsing and validation
- DBus API method signatures and return values
- Secret socket token generation and expiration
- Group exemption detection and logging

### Integration Testing (VM/Test Environment)
- **Plaintext USB workflow**:
  - Insert plaintext USB → daemon classifies and sets block-level read-only
  - Verify mount is read-only via udisksctl and file manager
  - Attempt write operations → should fail with EROFS
  - Attempt remount read-write → should be denied by polkit
  - Verify desktop notification appears with "Encrypt..." action
  - Check journald entries contain correct structured fields
  
- **LUKS2 encrypted workflow**:
  - Insert LUKS2 USB → daemon classifies as encrypted/locked
  - Verify notification with "Unlock..." action
  - Unlock via wizard/helper → should mount read-write
  - Write operations should succeed
  - Verify audit log entries for unlock success
  - Unmount and re-insert → should re-lock

- **Encryption wizard workflow**:
  - Run wizard on plaintext device
  - Test data preservation option (backup → encrypt → restore)
  - Test encryption without preservation (fresh format)
  - Verify passphrase validation (minimum length, confirmation match)
  - Monitor progress events via DBus
  - Verify LUKS2 container created with correct parameters (argon2id, AES-XTS-512)
  - Verify filesystem formatted (exfat/ext4) and mounted read-write
  - Check journald structured logging throughout process

- **LUKS1 handling**:
  - Insert LUKS1 device
  - Verify read-only mount (or blocked, depending on config)
  - Check log entries mark as LUKS1

- **Group exemption testing**:
  - Configure `exempted_groups = ["test-exempt"]`
  - Add user to group, verify enforcement bypassed
  - Check audit logs contain exemption reason and group name
  - Remove user from group, verify enforcement re-enabled

- **Headless operation**:
  - Test on system without GUI/display server
  - Verify daemon runs and enforces policies
  - Test DBus API operations from command-line (ListDevices, GetDeviceStatus)
  - Test unlock/encrypt via Python scripts using secret socket
  - Verify all operations work without GTK/UI components

### Regression Testing
- Non-USB block devices (internal disks, NVMe) → should be completely ignored
- Multiple partitions on same USB device → each evaluated independently
- `/dev/mapper/*` devices → should never be forced read-only
- Encrypted mapper removal during operation → cleanup should occur gracefully
- Config reload (SIGHUP) → should apply new settings without restart
- Service restart → should not affect already-mounted devices

### User Experience Testing
- Notifications appear consistently on all desktop environments (GNOME, KDE, XFCE, etc.)
- Wizard UI is usable and responsive during long operations
- Error messages are clear and include actionable information
- Help/Learn more content is accessible
- Progress indicators accurately reflect operation status
- Window/dialog focus behavior is correct

## 15) Related Documentation

- **[../README.md](../README.md)**: Main project README with installation instructions and quick start
- **[HEADLESS-USAGE.md](HEADLESS-USAGE.md)**: Complete guide for command-line usage on headless/server systems
- **[GROUP-EXEMPTIONS.md](GROUP-EXEMPTIONS.md)**: Detailed guide for configuring group-based exemptions
- **[../BUILD-RPM.md](../BUILD-RPM.md)**: Instructions for building RPM packages (Fedora, RHEL, openSUSE)
- **[../BUILD-DEB.md](../BUILD-DEB.md)**: Instructions for building DEB packages (Debian, Ubuntu)

## 16) Version History and Compatibility

**Current Version**: 1.0.0

### Feature Status
- ✅ Core enforcement (plaintext read-only, LUKS2 read-write)
- ✅ Desktop notifications and GTK4 wizard
- ✅ DBus API with secret socket for passphrases
- ✅ Group-based exemptions
- ✅ Data preservation during encryption
- ✅ Headless/server support
- ✅ RPM and DEB packaging (standard + bundled variants)
- ✅ Support for exfat, ext4, vfat filesystems
- ✅ Comprehensive journald audit logging
- ✅ Multi-partition device support

### Future Considerations
- Hardware token support (YubiKey, etc.) for LUKS unlocking
- Integration with enterprise key management systems
- TPM-based automatic unlock for specific trusted devices
- Web-based management interface for headless systems
- Policy enforcement via Active Directory/LDAP groups
- Support for additional encryption formats (VeraCrypt compatibility)

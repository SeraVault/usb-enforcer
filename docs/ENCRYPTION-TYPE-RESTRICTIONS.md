# Encryption Type Restrictions

## Overview

USB Enforcer supports restricting which encryption types are allowed to be unlocked. This is useful for organizations that want to standardize on a specific encryption format.

## Configuration Options

### `allow_luks2` (default: `true`)

Controls whether LUKS2 encrypted devices can be unlocked.

- **When `true`**: LUKS2 devices can be unlocked normally
- **When `false`**: Attempting to unlock a LUKS2 device will fail with "LUKS2 encrypted devices are not allowed by policy"

LUKS2 is the modern Linux encryption standard with improved security features over LUKS1.

### `allow_veracrypt` (default: `true`)

Controls whether VeraCrypt encrypted devices can be unlocked.

- **When `true`**: VeraCrypt devices can be unlocked normally
- **When `false`**: Attempting to unlock a VeraCrypt device will fail with "VeraCrypt encrypted devices are not allowed by policy"

VeraCrypt is cross-platform (Windows/Mac/Linux) and useful for devices that need to be shared across different operating systems.

### `allow_luks1_readonly` (default: `true`)

Controls whether older LUKS1 encrypted devices can be mounted (in read-only mode).

- **When `true`**: LUKS1 devices are allowed but mounted read-only
- **When `false`**: LUKS1 devices are completely blocked

LUKS1 is the older encryption format and should be migrated to LUKS2 for better security.

## Common Scenarios

### Scenario 1: Linux-Only Environment (LUKS2 Only)

If you want to only allow LUKS2 encryption:

```toml
allow_luks1_readonly = false
allow_luks2 = true
allow_veracrypt = false
default_encryption_type = "luks2"
```

Result:
- ✓ LUKS2 devices work normally
- ✗ VeraCrypt devices are rejected
- ✗ LUKS1 devices are rejected

### Scenario 2: Cross-Platform Environment (VeraCrypt Only)

If you need devices that work on Windows/Mac/Linux:

```toml
allow_luks1_readonly = false
allow_luks2 = false
allow_veracrypt = true
default_encryption_type = "veracrypt"
```

Result:
- ✓ VeraCrypt devices work normally
- ✗ LUKS2 devices are rejected
- ✗ LUKS1 devices are rejected

### Scenario 3: Migration Period (Allow Both)

During migration from LUKS to VeraCrypt or vice versa:

```toml
allow_luks1_readonly = true
allow_luks2 = true
allow_veracrypt = true
default_encryption_type = "veracrypt"  # or "luks2"
```

Result:
- ✓ All encryption types work
- New devices use the specified `default_encryption_type`

### Scenario 4: Maximum Security (LUKS2 Only, No Legacy)

Strictest configuration:

```toml
allow_luks1_readonly = false
allow_luks2 = true
allow_veracrypt = false
default_encryption_type = "luks2"
```

Result:
- ✓ Only modern LUKS2 encryption allowed
- ✗ All legacy and alternative formats rejected

## Configuration via Admin GUI

You can configure these settings using the admin GUI:

```bash
sudo usb-enforcer-admin
# or
sudo python3 src/usb_enforcer/ui/admin.py
```

Navigate to **Basic Enforcement** tab and toggle:
- **Allow LUKS1 (Read-Only)** - Enable/disable LUKS1 support
- **Allow LUKS2** - Enable/disable LUKS2 support  
- **Allow VeraCrypt** - Enable/disable VeraCrypt support

## Error Messages

When a user tries to unlock a device with a disabled encryption type:

```
ValueError: LUKS2 encrypted devices are not allowed by policy
ValueError: VeraCrypt encrypted devices are not allowed by policy
ValueError: LUKS1 encrypted devices are not allowed by policy
```

The device will not be unlocked and will remain inaccessible.

## Relationship to `default_encryption_type`

**Important distinction:**

- `default_encryption_type` - What format to use when **creating** new encrypted devices
- `allow_luks2` / `allow_veracrypt` - Which formats can be **unlocked/used**

Example:
```toml
default_encryption_type = "veracrypt"
allow_luks2 = true
allow_veracrypt = true
```

This means:
- New devices will be encrypted with VeraCrypt
- But both LUKS2 and VeraCrypt devices can be unlocked

## Deployment

After modifying `/etc/usb-enforcer/config.toml`, restart the daemon:

```bash
sudo systemctl restart usb-enforcer
```

Existing unlocked devices remain accessible. The new policy takes effect for new unlock attempts.

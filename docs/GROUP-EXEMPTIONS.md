# Group-Based USB Enforcement Exemptions

## Overview
The USB Encryption Enforcer now supports per-user exemptions based on Linux group membership. Administrators can designate specific groups whose members bypass all USB encryption enforcement, allowing trusted personnel to use plaintext USB drives with full read-write access while maintaining DLP restrictions for other users.

## How It Works
When a USB device is detected, the enforcement daemon checks if any currently logged-in user is a member of a group listed in the `exempted_groups` configuration. If a match is found:
- All enforcement is bypassed for that device
- The user has full read-write access without encryption requirements
- The exemption is logged with details about which user and group triggered it

## Configuration

### 1. Edit the config file
Add or modify the `exempted_groups` setting in `/etc/usb-enforcer/config.toml`:

```toml
# Group-based exemptions: Users in these groups will bypass USB encryption enforcement
exempted_groups = ["usb-exempt", "developers", "sysadmin"]
```

### 2. Create the exemption group
```bash
sudo groupadd usb-exempt
```

### 3. Add users to the group
```bash
sudo usermod -aG usb-exempt username
```

### 4. Restart the daemon
```bash
sudo systemctl restart usb-enforcerd
```

### 5. User login
Users must log out and back in for group membership changes to take effect.

## Quick Setup Script
A convenience script is provided to automate the setup:

```bash
sudo ./scripts/setup-exemption-group.sh
```

This script will:
- Create the `usb-exempt` group
- Optionally add a user to the group
- Update the config file (if not already configured)
- Offer to restart the daemon

## Use Cases
- **IT Administrators**: System maintenance personnel who need unrestricted USB access
- **Developers**: Development teams requiring frequent data transfers during testing
- **Trusted Personnel**: Staff with approved business needs for plaintext USB access
- **Emergency Access**: Temporary exemptions for specific projects or situations

## Security Considerations

### Best Practices
1. **Audit regularly**: Review group membership periodically
   ```bash
   getent group usb-exempt
   ```

2. **Limit membership**: Only add users who genuinely need exemption

3. **Monitor logs**: All exempted access is logged to journald with structured fields
   ```bash
   sudo journalctl -f | grep "USB_EE_EVENT"
   ```

4. **Time-limited access**: Consider using temporary group memberships for short-term needs

5. **Documentation**: Maintain records of who has exemptions and why

### Logging
When enforcement is bypassed, detailed log entries are created:
```
USB_EE_EVENT=enforce
DEVNODE=/dev/sdb1
CLASSIFICATION=plaintext
ACTION=exempt
RESULT=allow
exemption_reason=user 'alice' in exempted group 'usb-exempt'
```

View exemption logs:
```bash
# All USB enforcement events
sudo journalctl -t usb-enforcerd

# Filter for exemptions
sudo journalctl -t usb-enforcerd | grep "exempt"
```

## Group Management Commands

### View group members
```bash
getent group usb-exempt
```

### Add a user
```bash
sudo usermod -aG usb-exempt username
```

### Remove a user
```bash
sudo gpasswd -d username usb-exempt
```

### Delete the group
```bash
sudo groupdel usb-exempt
```

### Check user's groups
```bash
groups username
```

## Implementation Details

### Code Changes
1. **Config module** (`src/usb_enforcer/config.py`):
   - Added `exempted_groups` field to Config dataclass
   - Loads from TOML configuration

2. **User utilities** (`src/usb_enforcer/user_utils.py`):
   - Functions to detect active logged-in users
   - Check group membership for users
   - Determine if any active user is in an exempted group

3. **Enforcer** (`src/usb_enforcer/enforcer.py`):
   - Checks group exemptions before applying enforcement
   - Returns early with exemption status if user is exempted
   - Logs exemption reason for audit trail

### Multi-User Sessions
The implementation handles multiple logged-in users:
- Checks all active sessions (via `who` and `loginctl`)
- If ANY logged-in user is in an exempted group, enforcement is bypassed
- This ensures proper behavior in multi-user or remote session scenarios

### Primary vs Supplementary Groups
Group membership checking handles both:
- **Primary group**: User's main group (from `/etc/passwd`)
- **Supplementary groups**: Additional groups user belongs to (from `/etc/group`)

## Troubleshooting

### User added to group but exemption not working
**Problem**: Added user to group but enforcement still active
**Solution**: User must log out and log back in. Group membership is set at login.

```bash
# Verify current session groups (won't show new group until re-login)
groups

# Verify user is in group (this will show it)
getent group usb-exempt
```

### No users detected
**Problem**: Daemon logs show no active users found
**Solution**: Check that users are properly logged in

```bash
# Check logged-in users
who
loginctl list-sessions

# Check daemon logs
sudo journalctl -u usb-enforcerd -n 50
```

### Group doesn't exist
**Problem**: Config has group name but group not created
**Solution**: Create the group

```bash
sudo groupadd usb-exempt
```

### Config not loaded
**Problem**: Changes to config not taking effect
**Solution**: Restart the daemon

```bash
sudo systemctl restart usb-enforcerd

# Or reload config without restart (if supported)
sudo systemctl reload usb-enforcerd
```

## Testing

### Verify exemption is working
1. Add test user to exempted group:
   ```bash
   sudo usermod -aG usb-exempt testuser
   ```

2. Log in as testuser (or log out/in if already logged in)

3. Insert a plaintext USB drive

4. Check it's mounted read-write:
   ```bash
   mount | grep /dev/sd
   ```

5. Try writing to it:
   ```bash
   echo "test" > /media/testuser/USB-DRIVE/test.txt
   ```

6. Check logs for exemption:
   ```bash
   sudo journalctl -u usb-enforcerd | grep exempt
   ```

### Verify enforcement still works for non-exempted users
1. Log in as a regular user (not in exempted group)
2. Insert plaintext USB drive
3. Should be read-only
4. Write attempts should fail

## Migration from Previous Versions
If upgrading from a version without group exemptions:

1. The new config field is optional (defaults to empty list)
2. Existing configurations continue to work unchanged
3. No migration steps required unless you want to use the feature
4. Simply add `exempted_groups = []` to config if you want it explicitly set

## Example Scenarios

### Scenario 1: IT Department Exemption
```bash
# Create group for IT staff
sudo groupadd it-staff

# Add IT personnel
sudo usermod -aG it-staff alice
sudo usermod -aG it-staff bob

# Configure exemption
echo 'exempted_groups = ["it-staff"]' | sudo tee -a /etc/usb-enforcer/config.toml

# Restart daemon
sudo systemctl restart usb-enforcerd
```

### Scenario 2: Temporary Developer Access
```bash
# Use existing group
sudo usermod -aG usb-exempt developer1

# Developer logs in, completes work, then remove access
sudo gpasswd -d developer1 usb-exempt
```

### Scenario 3: Multiple Exemption Groups
```toml
# Different groups for different reasons
exempted_groups = ["sysadmin", "developers", "qa-team", "security-auditors"]
```

## Related Documentation
- Main documentation: [docs/usb-enforcer.md](../docs/usb-enforcer.md)
- Configuration reference: [deploy/config.toml.sample](../deploy/config.toml.sample)
- Setup script: [scripts/setup-exemption-group.sh](../scripts/setup-exemption-group.sh)

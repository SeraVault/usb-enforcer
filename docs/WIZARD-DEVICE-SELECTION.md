# USB Enforcer Wizard - Flexible Device Selection

## Overview

The USB Encryption Wizard has been enhanced to provide a better user experience with flexible device selection that adapts based on how it's launched.

## Changes Made

### 1. Dropdown Device Selection

**Before**: Used a `ListBox` showing all devices with checkboxes, which took up vertical space and required scrolling.

**After**: Uses a compact `DropDown` (ComboBox) that shows available USB devices in a dropdown menu.

### 2. Adaptive Behavior

The wizard now intelligently adapts based on the launch context:

#### Launched from Notification (with --device parameter)
```bash
/usr/libexec/usb-enforcer-wizard --device /dev/sdb
```
- Device dropdown shows only the specified device
- Dropdown is locked (not editable) since the device is pre-selected
- Refresh button is disabled
- User proceeds directly to entering passphrase

#### Launched from Application Menu (no device parameter)
```bash
/usr/libexec/usb-enforcer-wizard
```
- Device dropdown shows all available USB drives that can be encrypted
- Only "plaintext" (unencrypted) devices are shown
- User can select from the dropdown
- Refresh button is available to reload the device list
- First available device is auto-selected

### 3. Improved UI

- **Compact Layout**: Uniform window size (520x420) regardless of launch mode
- **Better Labels**: Device selection area has a clear "USB Device to Encrypt" heading
- **Refresh Icon**: Refresh button uses a symbolic icon for cleaner appearance
- **Smart Filtering**: Only shows devices that can actually be encrypted (plaintext classification)
- **Helpful Tooltips**: Added tooltips to guide users

### 4. Device Information

Each device in the dropdown shows:
- Device path (e.g., `/dev/sdb`)
- Device type if available (e.g., "USB Flash Drive")
- Serial number if available (for identification)

Example dropdown entry: `/dev/sdb - USB Flash Drive (Serial: 123456789ABC)`

## Technical Details

### Key Code Changes

1. **Removed `DeviceRow` class**: No longer needed with ComboBox approach
2. **Added `devices_cache`**: Stores full device info for selected index
3. **Unified refresh logic**: Single `refresh_devices()` method handles both modes
4. **ComboBox integration**: Uses `Gio.ListStore` with `Gtk.StringObject` for dropdown items

### Device Selection Logic

```python
# Get selected device from dropdown
selected_idx = self.device_combo.get_selected()
if selected_idx != Gtk.INVALID_LIST_POSITION and selected_idx < len(self.devices_cache):
    return self.devices_cache[selected_idx]
```

### Parent Device Handling

The wizard automatically handles partitions by showing the parent device:
- If `/dev/sdb1` is inserted, the wizard shows and encrypts `/dev/sdb` (parent disk)
- Ensures entire device is encrypted, not just a partition

## Benefits

1. **Cleaner UI**: Dropdown takes less space than a scrollable list
2. **Context-Aware**: Adapts seamlessly to notification vs. menu launch
3. **User-Friendly**: Clear what devices are available for encryption
4. **Consistent Size**: Window doesn't resize between modes
5. **Professional**: Follows modern UI patterns with dropdown selectors

## Testing

To test both modes:

```bash
# Test from app menu (shows dropdown with all devices)
/usr/libexec/usb-enforcer-wizard

# Test from notification (pre-selected device)
/usr/libexec/usb-enforcer-wizard --device /dev/sdb
```

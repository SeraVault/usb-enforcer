# Content Scanning Notifications

## Overview

USB Enforcer provides **real-time GUI notifications** for content scanning operations, alerting users when files are being scanned and when sensitive data is detected.

## Notification Types

### 1. Progress Notifications (During Scanning)

While files are being written to USB drives, a **floating progress window** displays:

- **File name** being scanned
- **Progress bar** showing scan completion percentage
- **Status** (Scanning, Blocked, Allowed)
- **File size** and bytes scanned
- **Scan speed** (MB/s)
- **Pattern count** checked

**Visual Example:**
```
┌─────────────────────────────────────────┐
│ Scanning File for Sensitive Data       │
├─────────────────────────────────────────┤
│ document.pdf                            │
│ [████████████░░░░░░] 65.2%             │
│ 🔍 Scanning for sensitive data...      │
│                                         │
│ ▶ Details                               │
│   Size: 6.5 MB / 10.0 MB               │
│   Speed: 2.3 MB/s                       │
│   Patterns checked: 25                  │
└─────────────────────────────────────────┘
```

**Behavior:**
- Appears automatically when file writing begins
- Updates in real-time as scanning progresses
- **Auto-closes after 3 seconds** if file is clean
- Stays open if file is blocked (requires manual close)

### 2. Blocked File Notifications (Urgent)

When sensitive data is detected, an **urgent desktop notification** appears:

**Visual Example:**
```
┌─────────────────────────────────────────────────────┐
│ 🚫 USB File Blocked - Sensitive Data Detected      │
├─────────────────────────────────────────────────────┤
│ File: employee_data.xlsx                            │
│                                                     │
│ ❌ This file was prevented from being written      │
│    to your USB drive.                               │
│                                                     │
│ 🔍 Detected: 15 instance(s) of sensitive data      │
│ 📋 Patterns found: ssn (pii), credit_card          │
│                    (financial), api_key (corporate) │
│                                                     │
│ ⚠️  Writing files with sensitive data to USB       │
│    drives is prohibited by policy.                  │
│    Please remove sensitive information before       │
│    copying to removable media.                      │
└─────────────────────────────────────────────────────┘
```

**Details Shown:**
- **File name** that was blocked
- **Number of matches** found
- **Pattern categories** detected (PII, Financial, Corporate)
- **Specific pattern types** (SSN, credit card, API keys, etc.)
- **Policy reminder** about sensitive data

**Behavior:**
- **URGENT priority** - appears prominently on desktop
- Stays visible until user dismisses
- Logged to system logs for audit trail

### 3. Allowed File Notifications (Silent)

When files pass scanning:
- ✅ Status shown in progress window
- **Auto-closes after 3 seconds**
- No separate desktop notification (non-intrusive)
- Logged for audit purposes

## Implementation Details

### Progress Window Features

The progress notification window is implemented using **GTK 4** with:

1. **Real-time updates** - Progress bar updates as bytes are scanned
2. **Speed calculation** - Shows MB/s scan rate
3. **Smart auto-close** - Disappears automatically for clean files
4. **Manual dismiss** - User can close at any time
5. **Details expander** - Click to see technical details

### Blocked Notification System

The blocked notification system:

1. **Intercepts at write time** - Blocks before data reaches disk
2. **Pattern analysis** - Identifies specific sensitive data types
3. **Multi-level alerting**:
   - Progress window shows "BLOCKED" status
   - Desktop notification provides details
   - System log records full audit trail
4. **Privacy-safe** - Never shows actual sensitive values in notifications

### Technical Architecture

```
┌──────────────────┐
│  FUSE Overlay    │  Intercepts write operations
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Content Scanner  │  Scans for patterns
└────────┬─────────┘
         │
         ├─────────────────────┐
         ▼                     ▼
┌──────────────────┐  ┌────────────────────┐
│ Progress         │  │ Blocked            │
│ Callback         │  │ Callback           │
└────────┬─────────┘  └────────┬───────────┘
         │                     │
         ▼                     ▼
┌──────────────────┐  ┌────────────────────┐
│ ScanProgress     │  │ BlockedNotification│
│ Notifier         │  │ Service            │
└────────┬─────────┘  └────────┬───────────┘
         │                     │
         └──────────┬──────────┘
                    ▼
         ┌──────────────────────┐
         │  GTK 4 Application   │
         │  (User Desktop)      │
         └──────────────────────┘
```

## Configuration

Notifications are controlled by the content scanning configuration:

```toml
[content_scanning]
enabled = true
block_on_detection = true  # Show blocked notifications

# These settings affect what triggers notifications:
enabled_categories = ["pii", "financial", "corporate"]
```

## User Experience

### Typical Workflow

1. **User copies file to USB**
   ```
   $ cp sensitive_document.pdf /media/usb/
   ```

2. **Progress notification appears**
   - Shows scanning progress
   - User can continue working
   - Non-blocking operation

3. **If sensitive data detected:**
   - Progress window shows "BLOCKED" status
   - Urgent desktop notification appears
   - File write fails with "Permission denied"
   - Original file deleted from USB
   - User informed of what was detected

4. **If file is clean:**
   - Progress window shows "ALLOWED" status
   - Auto-closes after 3 seconds
   - File written successfully
   - No further user action needed

### Benefits

✅ **Transparent** - Users see exactly what's happening
✅ **Informative** - Know why files are blocked
✅ **Non-intrusive** - Clean files don't require interaction
✅ **Secure** - Sensitive values never displayed
✅ **Auditable** - All actions logged

## Examples

### SSN Detection

File containing Social Security Numbers:
```
File: employee_roster.xlsx
Detected: 23 instance(s) of sensitive data
Patterns found: ssn (pii)
```

### Credit Card Detection

File with payment information:
```
File: transactions.csv
Detected: 47 instance(s) of sensitive data
Patterns found: credit_card (financial), bank_account (financial)
```

### Multi-Pattern Detection

File with multiple sensitive data types:
```
File: customer_database_backup.sql
Detected: 156 instance(s) of sensitive data
Patterns found: ssn (pii), email (pii), credit_card (financial),
                bank_account (financial), api_key (corporate)
```

## Testing Notifications

To test the notification system:

```bash
# 1. Start the daemon
sudo usb-enforcerd

# 2. In another terminal, insert encrypted USB
# (or use test suite with virtual devices)

# 3. Try copying a file with sensitive data
echo "SSN: 123-45-6789" > /tmp/test.txt
cp /tmp/test.txt /media/usb-enforcer/

# Expected: Progress window appears, then blocked notification
```

## Troubleshooting

### Notifications Not Appearing

**Check GTK 4 is installed:**
```bash
dnf list installed | grep gtk4
```

**Check notification service is running:**
```bash
ps aux | grep usb-enforcer-ui
```

**Check daemon logs:**
```bash
journalctl -u usb-enforcerd -f
```

### Progress Window Stays Open

This is normal for blocked files - user must manually close.

For allowed files, window should auto-close after 3 seconds.

## API Reference

### Progress Callback

```python
def progress_callback(filepath: str, progress: float, status: str,
                     total_size: int, scanned_size: int):
    """
    Called during file scanning.
    
    Args:
        filepath: Path to file being scanned
        progress: Percentage complete (0-100)
        status: 'scanning', 'blocked', 'allowed', or 'error'
        total_size: Total file size in bytes
        scanned_size: Bytes scanned so far
    """
```

### Blocked Callback

```python
def blocked_callback(filepath: str, reason: str, patterns: str, 
                    match_count: int):
    """
    Called when file is blocked.
    
    Args:
        filepath: Path to blocked file
        reason: Human-readable reason
        patterns: Comma-separated pattern names
        match_count: Number of matches found
    """
```

## Privacy Considerations

**What's Shown in Notifications:**
- ✅ File names
- ✅ Pattern types (e.g., "ssn", "credit_card")
- ✅ Pattern categories (e.g., "pii", "financial")
- ✅ Match counts

**What's NEVER Shown:**
- ❌ Actual sensitive values (SSNs, credit cards, etc.)
- ❌ File contents
- ❌ Context around matches

All sensitive values are redacted from notifications for privacy and security.

## Future Enhancements

Planned improvements:

- [ ] Sound alerts for blocked files
- [ ] Configurable notification timeout
- [ ] Notification history viewer
- [ ] Pattern-specific notification customization
- [ ] Integration with system notification center
- [ ] Email alerts for administrators

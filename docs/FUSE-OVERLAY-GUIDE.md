# FUSE Overlay and Content Scanning Integration

## Overview

The USB Enforcer now includes **real-time content scanning** using a FUSE (Filesystem in Userspace) overlay. This prevents sensitive data from being written to USB devices by intercepting all write operations and scanning content **before** it reaches the physical device.

## How It Works

### Architecture

```
User Application
    ↓ write()
FUSE Overlay Mount Point (/media/usb)
    ↓ buffer & scan
Content Scanner (patterns, archives, documents)
    ↓ allow/block
Real Device Mount (.real/)
    ↓ write to disk
Physical USB Device
```

### Write Interception Flow

1. **User writes file** to mounted USB device
2. **FUSE intercepts write** operation and buffers data in memory
3. **On file close**, FUSE triggers content scan:
   - Text pattern matching (SSN, credit cards, API keys, etc.)
   - Archive extraction and recursive scanning (ZIP, TAR, 7Z, RAR)
   - Document text extraction (PDF, DOCX, XLSX, PPTX, ODF)
   - N-gram and entropy analysis for unknown patterns
4. **Scan result**:
   - **BLOCKED**: File contains sensitive data → Write rejected, file not written
   - **ALLOWED**: No sensitive data → Write proceeds to device
5. **GUI notification** shows scan progress and result

### Key Features

- **Transparent**: Applications don't need modification
- **Real-time**: Scans happen during write, not after
- **Performant**: 3-tier scanning strategy based on file size
- **Cached**: Identical files scanned once using content hashing
- **Comprehensive**: Scans text, archives, documents, images (via OCR)
- **Configurable**: Enable/disable scanning, customize patterns, set action mode

## Installation

### Prerequisites

The FUSE overlay requires additional Python packages:

```bash
pip install -r requirements.txt
```

Key dependencies:
- `fusepy>=3.0.1` - FUSE Python bindings
- `pdfplumber>=0.10.0` - PDF text extraction
- `python-docx>=1.0.0` - Word document parsing
- `openpyxl>=3.1.0` - Excel spreadsheet parsing
- `python-pptx>=0.6.23` - PowerPoint parsing
- `odfpy>=1.4.1` - OpenDocument format support
- `py7zr>=0.20.0` - 7-Zip archive support
- `rarfile>=4.1` - RAR archive support

### System Requirements

- Linux kernel with FUSE support (CONFIG_FUSE_FS=y)
- User must have permission to mount FUSE filesystems
- Minimum 512MB RAM for content scanning cache

## Configuration

### Enable Content Scanning

Edit `/etc/usb-enforcer/config.toml`:

```toml
[content_scanning]
enabled = true
action = "block"  # "block", "warn", or "log_only"
cache_enabled = true
cache_max_size_mb = 100

enabled_categories = [
    "financial",      # Credit cards, bank accounts
    "personal",       # SSN, passports, licenses
    "authentication", # API keys, passwords, tokens
    "medical"        # Medical records, insurance IDs
]

# Archive scanning
archive_scanning_enabled = true
max_archive_depth = 5
max_archive_members = 1000

# Document scanning
document_scanning_enabled = true

# N-gram analysis
ngram_analysis_enabled = true
min_entropy_threshold = 4.0
suspicious_ngram_threshold = 0.7

# Performance
max_file_size_mb = 100
scan_timeout_seconds = 30
max_concurrent_scans = 2
```

### Action Modes

- **block**: Reject writes containing sensitive data (default)
- **warn**: Log warning but allow write (auditing mode)
- **log_only**: Log all scans, don't block anything (testing mode)

### Custom Patterns

Add custom detection patterns:

```toml
[[content_scanning.custom_patterns]]
name = "internal_employee_id"
description = "Internal employee ID format"
category = "personal"
regex = "EMP-\\d{6}"

[[content_scanning.custom_patterns]]
name = "project_code"
description = "Confidential project code"
category = "authentication"
regex = "PROJ-[A-Z]{3}-\\d{4}"
validator = "validate_project_code"  # Optional custom validator
```

## GUI Notifications

### Notification Service

The notification service shows real-time scan progress in a GTK window:

![Scan Progress Window](images/scan-progress.png)

**Features:**
- File name being scanned
- Progress bar (0-100%)
- Status indicator (scanning, blocked, allowed, error)
- File size and scan speed
- Pattern count
- Details expander with additional info

### Running Notifications

**As user (recommended):**

```bash
usb-enforcer-notifications
```

This starts a background GTK application that listens for DBus scan progress signals and displays notifications.

**Autostart on login:**

Copy the desktop file to autostart:

```bash
mkdir -p ~/.config/autostart
cp /usr/share/applications/usb-enforcer-notifications.desktop ~/.config/autostart/
```

Or add to your DE's startup applications:
- **GNOME**: Settings → Apps → Startup Applications
- **KDE**: System Settings → Startup and Shutdown → Autostart
- **XFCE**: Settings → Session and Startup → Application Autostart

### Notification Types

1. **Progress Window**: Shows while scanning large files
   - Progress bar with percentage
   - Estimated time remaining
   - Real-time status updates

2. **Desktop Notification**: Urgent notification when file is blocked
   - Title: "USB File Blocked"
   - Body: File name and reason
   - Priority: URGENT

3. **Success (silent)**: Allowed files don't trigger notifications
   - Only logged to journal
   - Window auto-closes after 3 seconds

## Usage

### Normal Usage (Transparent)

Content scanning is completely transparent to users:

1. **Unlock USB device** (if encrypted)
2. **Copy files** to USB normally
3. **Files are scanned** automatically on write
4. **Blocked files** rejected with notification
5. **Allowed files** written to device

Example:

```bash
# User copies file with SSN
cp sensitive-document.txt /media/user/usb-drive/

# FUSE intercepts write
# Scanner detects SSN pattern
# Write is BLOCKED
# Notification shown: "File contains Social Security Number"
# File is NOT written to USB

# User copies clean file
cp presentation.pdf /media/user/usb-drive/

# FUSE intercepts write
# Scanner finds no sensitive data
# Write is ALLOWED
# File is written to USB
# Window auto-closes
```

### Command-Line Testing

Test scanner without mounting:

```bash
# Scan a file
usb-enforcer-cli scan /path/to/file.txt

# Scan text directly
usb-enforcer-cli scan-text "SSN: 123-45-6789"

# List available patterns
usb-enforcer-cli patterns

# Test specific pattern
usb-enforcer-cli test-pattern ssn "123-45-6789"
```

### Monitoring Statistics

Check scan statistics via DBus:

```bash
# Get statistics
busctl call org.seravault.UsbEnforcer \
    /org/seravault/UsbEnforcer \
    org.seravault.UsbEnforcer \
    GetScannerStatistics

# Watch scan progress signals
busctl monitor org.seravault.UsbEnforcer \
    --match="type='signal',interface='org.seravault.UsbEnforcer',member='ScanProgress'"
```

## Performance

### Scanning Strategy

The scanner uses a 3-tier approach based on file size:

**Small files (<1MB):**
- Full content scan in memory
- All patterns checked
- < 1ms typical scan time

**Medium files (1-10MB):**
- Chunked scanning (1MB chunks)
- 1KB overlap between chunks
- ~10ms per MB

**Large files (>10MB):**
- Sampled scanning
- First 1MB + random 1MB samples
- Fast approximate detection
- ~50ms regardless of size

### Caching

Scan results are cached using SHA-256 content hashing:

- **Cache hit**: < 0.1ms (no rescan needed)
- **Cache size**: Configurable (default 100MB)
- **Eviction**: LRU (Least Recently Used)
- **Persistence**: In-memory only (cleared on daemon restart)

### Throughput

**Typical throughput** (Intel Core i5, SSD):
- Plain text: ~100 MB/s
- PDF documents: ~50 MB/s
- ZIP archives: ~30 MB/s (decompression overhead)
- Encrypted archives: ~20 MB/s

**Bottlenecks:**
- Document text extraction (PDF parsing)
- Archive decompression (ZIP, 7Z)
- Regex pattern matching (many patterns)

**Optimization tips:**
- Disable document scanning if not needed
- Reduce max_archive_depth for faster ZIP scans
- Increase max_file_size_mb to skip huge files
- Disable categories you don't need

## Security

### Threat Model

**Prevents:**
- Accidental data leaks (copy-paste errors)
- Naive exfiltration attempts (copying files)
- Insider threats (copying customer data)

**Does NOT prevent:**
- Steganography (hiding data in images)
- Encrypted exfiltration (password-protected archives)
- Obfuscated data (base64, rot13, custom encoding)
- Screen capture or photos
- Network exfiltration

### Privacy

The scanner is designed with privacy in mind:

- **No data storage**: Scan results logged, not file contents
- **Local processing**: All scanning happens on local machine
- **Anonymized logs**: Only pattern types logged, not actual data
- **Opt-in**: Content scanning disabled by default
- **Configurable**: Admins choose what to scan for

Example log entry:

```
scan_result: BLOCKED - patterns=['ssn', 'credit_card'] file_size=1234
```

Not logged: Actual SSN or credit card numbers

### Bypass Prevention

The FUSE overlay prevents common bypass attempts:

- **Direct device access**: Blocked by udev rules (read-only)
- **Unmount and remount**: Requires root, remount restores overlay
- **Kill daemon**: Device becomes read-only
- **Modify cache**: Cache uses cryptographic hashing
- **Race conditions**: Write buffering prevents partial writes

## Troubleshooting

### Content Scanning Not Working

**Check if enabled:**

```bash
grep -A 10 "\[content_scanning\]" /etc/usb-enforcer/config.toml
```

Should show `enabled = true`

**Check daemon logs:**

```bash
sudo journalctl -u usb-enforcerd -f
```

Look for:
- "Content scanner initialized"
- "FUSE manager initialized"
- "Setting up FUSE overlay for /media/..."

**Check FUSE mount:**

```bash
mount | grep fuse
```

Should show overlay mount at USB mount point

### Notifications Not Showing

**Check notification service:**

```bash
ps aux | grep usb-enforcer-notifications
```

**Start manually:**

```bash
usb-enforcer-notifications --debug
```

**Check DBus connection:**

```bash
busctl list | grep UsbEnforcer
```

Should show `org.seravault.UsbEnforcer`

### Scan Errors

**Check dependencies:**

```bash
python3 -c "import fusepy, pdfplumber, docx, openpyxl; print('OK')"
```

**Check file permissions:**

```bash
ls -la /path/to/blocked/file
```

Must be readable by root (daemon runs as root)

**Check scan timeout:**

Increase `scan_timeout_seconds` in config for large files

### Performance Issues

**Reduce scanning overhead:**

```toml
[content_scanning]
# Disable document scanning
document_scanning_enabled = false

# Skip large files
max_file_size_mb = 50

# Reduce patterns
enabled_categories = ["financial"]  # Only scan for financial data

# Disable n-gram analysis
ngram_analysis_enabled = false
```

**Monitor scan time:**

```bash
sudo journalctl -u usb-enforcerd | grep "scan_time_ms"
```

**Check cache hit rate:**

```bash
busctl call org.seravault.UsbEnforcer \
    /org/seravault/UsbEnforcer \
    org.seravault.UsbEnforcer \
    GetScannerStatistics
```

Look for `cache_hit_rate` (should be >50% for good performance)

## Advanced Usage

### Custom Validators

Add Python validator functions for custom patterns:

```python
# /etc/usb-enforcer/validators.py

def validate_project_code(text: str) -> bool:
    """Validate project code format"""
    # Extract project code
    match = re.search(r'PROJ-([A-Z]{3})-(\d{4})', text)
    if not match:
        return False
    
    dept, number = match.groups()
    
    # Check if department code is valid
    valid_depts = ['ENG', 'SAL', 'MKT', 'FIN']
    if dept not in valid_depts:
        return False
    
    # Check if number is in valid range
    if not (1000 <= int(number) <= 9999):
        return False
    
    return True
```

Reference in config:

```toml
[[content_scanning.custom_patterns]]
name = "project_code"
regex = "PROJ-[A-Z]{3}-\\d{4}"
validator = "validators.validate_project_code"
```

### Integration with SIEM

Forward scan events to SIEM:

```bash
# Use journald CEF format
sudo journalctl -u usb-enforcerd -f -o json | \
    jq -r 'select(.SCAN_RESULT) | 
           "CEF:0|Seravault|USB Enforcer|1.0|SCAN|\(.SCAN_RESULT)|\(.SEVERITY)|
            file=\(.FILE_PATH) patterns=\(.PATTERNS) size=\(.FILE_SIZE)"' | \
    nc siem.example.com 514
```

### Prometheus Metrics

Export scan metrics:

```python
# Custom exporter
from prometheus_client import Counter, Histogram, start_http_server

scans_total = Counter('usb_enforcer_scans_total', 'Total scans', ['result'])
scan_duration = Histogram('usb_enforcer_scan_duration_seconds', 'Scan duration')

# Query via DBus and expose metrics
start_http_server(9090)
```

## See Also

- [Content Verification Whitepaper](CONTENT-VERIFICATION-WHITEPAPER.md)
- [Implementation Summary](CONTENT-VERIFICATION-IMPLEMENTATION.md)
- [Integration Guide](CONTENT-SCANNING-INTEGRATION.md)
- [Pattern Library Reference](../src/usb_enforcer/content_verification/patterns.py)

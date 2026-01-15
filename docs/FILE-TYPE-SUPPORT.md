# File Type Support - Content Scanning

This document details the comprehensive file type support in USB Enforcer's content scanning system, including protection against extension spoofing attacks.

## Overview

USB Enforcer scans **35+ file formats** across multiple categories to detect sensitive data before it's written to USB devices. The system uses both **extension-based detection** and **magic number validation** to prevent evasion attempts.

---

## Anti-Evasion Protection

### Magic Number Validation

To prevent users from bypassing scanning by renaming files (e.g., `passwords.txt` → `passwords.jpg`), the scanner validates file types using **magic numbers** (file signatures):

```python
# Example: File claims to be .jpg but is actually text
real_type = detect_via_magic_numbers(file)  # Returns: "text/plain"
claimed_ext = ".jpg"

if mismatch_detected(claimed_ext, real_type):
    # Force full scan despite .jpg being in SKIP_EXTENSIONS
    logger.warning("Extension spoofing detected!")
    scan_file_contents(file)
```

**Detection Examples:**
- `secrets.txt` renamed to `secrets.jpg` → **Detected as text/plain, scanned**
- `passwords.csv` renamed to `passwords.mp4` → **Detected as text/csv, scanned**
- `api-keys.json` renamed to `api-keys.exe` → **Detected as application/json, scanned**

**Technology:** Uses `python-magic` library (libmagic) to read the first few bytes of files and identify actual content type regardless of extension.

---

## Supported File Categories

### 1. Text & Configuration Files (22 formats)

**Always scanned** - High risk for containing plaintext secrets:

| Extension | Description | Pattern Detection |
|-----------|-------------|-------------------|
| `.txt` | Plain text | All patterns |
| `.csv` | Comma-separated values | All patterns |
| `.json` | JSON data | API keys, tokens, PII |
| `.xml` | XML documents | All patterns |
| `.yaml`, `.yml` | YAML config | API keys, credentials |
| `.toml` | TOML config | API keys, credentials |
| `.ini`, `.conf`, `.cfg` | Config files | Database strings, keys |
| `.env` | Environment vars | API keys, passwords |
| `.log` | Log files | Credentials, PII |
| `.sql` | SQL scripts | Database credentials |
| `.sh`, `.bat`, `.ps1` | Shell scripts | Hardcoded credentials |
| `.py`, `.js`, `.java` | Source code | API keys, tokens |
| `.key`, `.pem` | Cryptographic keys | Private keys, certificates |
| `.eml` | Email messages (RFC 822) | All patterns |

### 2. Archive Formats (13 formats)

**Recursively extracted and scanned:**

| Extension | Format | Handler | Notes |
|-----------|--------|---------|-------|
| `.zip` | ZIP archive | zipfile (stdlib) | Most common format |
| `.jar` | Java Archive | zipfile | ZIP-based, treated as ZIP |
| `.war` | Web Application Archive | zipfile | ZIP-based |
| `.ear` | Enterprise Archive | zipfile | ZIP-based |
| `.tar` | TAR archive | tarfile (stdlib) | Unix standard |
| `.tar.gz`, `.tgz` | Gzipped TAR | tarfile | Common Linux format |
| `.tar.bz2`, `.tbz2` | Bzip2 TAR | tarfile | Better compression |
| `.tar.xz`, `.txz` | XZ TAR | tarfile | Best compression |
| `.gz` | Gzip (standalone) | gzip (stdlib) | Single file compression |
| `.bz2` | Bzip2 (standalone) | bz2 (stdlib) | Single file compression |
| `.xz` | XZ (standalone) | lzma (stdlib) | Single file compression |
| `.7z` | 7-Zip | py7zr | High compression |
| `.rar` | RAR archive | rarfile | Requires unrar binary |

**Security Features:**
- Depth limit (default: 5 levels) to prevent nesting attacks
- Member count limit (default: 1000 files) to prevent zip bombs
- Size limit (default: 100 MB per extracted file)
- Timeout protection (default: 30 seconds per archive)
- Encrypted archive detection (blocks if policy requires)

### 3. Office Documents (10 formats)

**Text extracted and scanned:**

#### Modern Office (Office 2007+)
| Extension | Format | Handler | Coverage |
|-----------|--------|---------|----------|
| `.docx` | Word Document | python-docx | Paragraphs, tables, headers |
| `.xlsx` | Excel Spreadsheet | openpyxl | All sheets, cells, formulas |
| `.pptx` | PowerPoint | python-pptx | Slides, notes, shapes |

#### Legacy Office (Office 97-2003)
| Extension | Format | Handler | Coverage |
|-----------|--------|---------|----------|
| `.doc` | Old Word | olefile | Basic detection (OLE2) |
| `.xls` | Old Excel | xlrd | All worksheets and cells |
| `.ppt` | Old PowerPoint | olefile | Basic detection (OLE2) |

#### OpenDocument Formats
| Extension | Format | Handler | Coverage |
|-----------|--------|---------|----------|
| `.odt` | Text Document | odfpy | Paragraphs, tables |
| `.ods` | Spreadsheet | odfpy | All sheets and cells |
| `.odp` | Presentation | odfpy | Slides and content |

#### Other Documents
| Extension | Format | Handler | Coverage |
|-----------|--------|---------|----------|
| `.pdf` | PDF Document | pdfplumber | Text extraction (all pages) |
| `.rtf` | Rich Text Format | striprtf | Text with formatting removed |
| `.msg` | Outlook Message | extract-msg | Subject, sender, body, attachments |

**Note:** Legacy Office formats (.doc, .ppt) use basic OLE2 detection. Full text extraction would require external tools like `antiword`. Currently, these are detected but not deeply parsed.

---

## Files Explicitly Skipped

The following binary formats are **never scanned** (unless extension mismatch is detected):

### Disk Images
- `.iso`, `.img`, `.vmdk`, `.vdi`, `.qcow2`

### Multimedia
- **Video:** `.mp4`, `.avi`, `.mkv`
- **Audio:** `.mp3`, `.wav`, `.flac`
- **Images:** `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.ico`

### Executables
- `.exe`, `.dll`, `.so`, `.dylib`

**Rationale:** These formats cannot contain plaintext secrets and scanning them would waste CPU cycles. However, if a text file is **renamed** to use one of these extensions, the magic number validation will detect the mismatch and force a scan.

---

## Detection Patterns

All scanned files are checked for 25+ patterns across three categories:

### Personal Identifiable Information (PII)
- Social Security Numbers (SSN)
- Email addresses
- Phone numbers
- Passport numbers
- Driver's license numbers
- Credit card numbers (Luhn validated)
- Bank account numbers

### Financial Data
- Credit/debit card numbers (all major networks)
- CVV/CVV2 codes
- Bank routing numbers
- IBAN numbers
- Bitcoin addresses
- Cryptocurrency wallet addresses

### Corporate Secrets
- API keys (AWS, Azure, GCP, GitHub, etc.)
- JWT tokens
- OAuth tokens
- Private keys (RSA, SSH)
- Database connection strings
- Password patterns

---

## Configuration

### File Type Scanning Control

In `/etc/usb-enforcer/config.toml`:

```toml
[content_scanning]
enabled = true

# Size limits
max_file_size_mb = 500          # Skip files larger than this
max_scan_time_seconds = 30       # Timeout for long scans

# Archive settings
[content_scanning.archives]
max_depth = 5                    # Recursive extraction depth
max_members = 1000               # Files per archive
max_extract_size_mb = 100        # Max size per extracted file
block_encrypted_archives = false # Block password-protected archives
```

### Custom Patterns

Add organization-specific patterns:

```toml
[[content_scanning.custom_patterns]]
name = "employee_id"
regex = "EMP-\\d{6}"
description = "Internal employee ID"
severity = "high"
category = "pii"
```

### Disable Specific Patterns

```toml
[content_scanning]
disabled_patterns = ["phone_number", "email"]  # Too many false positives
```

---

## Performance Characteristics

| File Size | Scan Time | Method |
|-----------|-----------|--------|
| < 1 MB | < 10ms | Full in-memory scan |
| 1-10 MB | 10-50ms | Buffered read |
| 10-100 MB | 50-200ms | Streaming with sampling |
| > 100 MB | 200ms+ | Chunked scan with early exit |

**Archive Overhead:** ~50-100ms per archive for extraction + scan time per member

**Document Parsing:** ~20-80ms depending on document complexity

---

## Dependencies

### Python Packages (16 total)
```
python-magic>=0.4.27      # Magic number detection
pdfplumber>=0.10.0        # PDF text extraction
python-docx>=1.0.0        # DOCX parsing
openpyxl>=3.1.0           # XLSX parsing
python-pptx>=0.6.0        # PPTX parsing
odfpy>=1.4.0              # ODF formats
py7zr>=0.20.0             # 7z archives
rarfile>=4.1              # RAR archives
fusepy>=3.0.1             # FUSE filesystem
xlrd>=2.0.0               # Old Excel (.xls)
olefile>=0.46             # OLE2 detection (.doc, .ppt)
extract-msg>=0.41.0       # Outlook .msg files
striprtf>=0.0.26          # RTF text extraction
```

### System Libraries
```bash
# Debian/Ubuntu
apt install libmagic1 fuse3 libfuse3-3 unrar

# RHEL/Fedora
dnf install file-libs fuse3 fuse3-libs unrar
```

---

## Security Considerations

### 1. Archive Bomb Protection
- Limits on extraction depth, member count, and extracted size
- Timeout protection for long-running extractions
- Early termination on suspicious patterns

### 2. Privacy Protection
- Matched patterns are **never logged** to disk
- Only pattern names and positions are recorded
- File hashes used for cache, not content

### 3. Resource Limits
- Maximum file size prevents DoS via huge files
- Maximum scan time prevents CPU exhaustion
- Cache limits prevent memory exhaustion

### 4. Extension Validation
- Magic number checking prevents simple evasion
- Mismatches trigger security warnings
- Files claiming exempt extensions are validated

---

## Troubleshooting

### Issue: Files not being scanned

**Check 1:** Is content scanning enabled?
```bash
grep "enabled = true" /etc/usb-enforcer/config.toml
```

**Check 2:** Is file too large?
```bash
# Check max_file_size_mb setting
grep "max_file_size_mb" /etc/usb-enforcer/config.toml
```

**Check 3:** Is python-magic installed?
```bash
python3 -c "import magic; print('OK')"
```

### Issue: False positives

**Solution:** Disable specific patterns:
```toml
[content_scanning]
disabled_patterns = ["email", "phone_number"]
```

Or adjust sensitivity in pattern definitions.

### Issue: Slow performance

**Solution 1:** Reduce max file size:
```toml
max_file_size_mb = 100  # Instead of 500
```

**Solution 2:** Reduce archive depth:
```toml
[content_scanning.archives]
max_depth = 3  # Instead of 5
```

### Issue: "python-magic not installed" warnings

**Solution:** Install system library:
```bash
# Debian/Ubuntu
sudo apt install libmagic1

# RHEL/Fedora
sudo dnf install file-libs
```

Then reinstall Python package:
```bash
/usr/lib/usb-enforcer/.venv/bin/pip install python-magic>=0.4.27
```

---

## Examples

### Example 1: Detecting Renamed Text File

```bash
# User tries to evade scanning
cp api-keys.txt vacation-photo.jpg

# System detects mismatch
[WARNING] Extension mismatch: vacation-photo.jpg claims .jpg but is text/plain
[BLOCKED] Sensitive data detected in vacation-photo.jpg
  - Pattern: api_key (corporate)
  - Matches: 3
```

### Example 2: Scanning ZIP Archive

```bash
# User creates archive
zip backup.zip passwords.txt config.yaml database.sql

# System recursively scans
[INFO] Scanning archive: backup.zip (3 members)
[BLOCKED] Sensitive data in backup.zip:passwords.txt
  - Pattern: password_pattern (corporate)
  - Matches: 12
```

### Example 3: Excel Spreadsheet with SSNs

```bash
# User exports employee data
cp employee-list.xlsx /media/usb-enforcer/

# System extracts and scans all cells
[BLOCKED] Sensitive data in employee-list.xlsx
  - Pattern: ssn (pii)
  - Matches: 47
```

---

## Future Enhancements

### Planned Additions
- Machine learning-based classification
- OCR for image-embedded text
- More granular MIME type validation
- Improved .doc/.ppt text extraction
- Support for additional archive formats (.cab, .ace)

### Under Consideration
- Database file scanning (.sqlite, .db)
- Binary pattern matching (non-text secrets)
- Cloud-based threat intelligence integration
- Real-time file fingerprinting

---

## See Also

- [Content Verification Whitepaper](CONTENT-VERIFICATION-WHITEPAPER.md) - System architecture
- [Content Scanning Integration](CONTENT-SCANNING-INTEGRATION.md) - Implementation details
- [Administration Guide](ADMINISTRATION.md) - Configuration examples
- [Testing Guide](CONTENT-SCANNING-TESTS.md) - Test suite documentation

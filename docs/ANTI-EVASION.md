# Anti-Evasion Security Features

This document explains the security mechanisms that prevent users from circumventing USB Enforcer's content scanning system.

---

## Threat Model

### Attack Scenario
A user attempts to exfiltrate sensitive data by bypassing the content scanner through various evasion techniques:

1. **Extension Spoofing**: Renaming `passwords.txt` to `passwords.jpg` to trick the scanner into thinking it's an image
2. **Archive Nesting**: Creating deeply nested archives to exhaust scanner resources
3. **Compression Bombs**: Crafting malicious archives that expand exponentially
4. **Encrypted Archives**: Password-protecting archives to hide contents
5. **Size-based Evasion**: Splitting data across many small files under detection thresholds

---

## Defense Mechanisms

### 1. Magic Number Validation

**Problem**: User renames text files to have exempt extensions (images, videos, executables).

**Solution**: Read file signatures (magic numbers) from the first bytes of files to determine actual content type, regardless of extension.

```python
# Example evasion attempt:
mv api-keys.txt api-keys.jpg  # User tries to trick scanner

# Defense:
real_type = detect_magic_number("api-keys.jpg")
# Returns: "text/plain"

claimed_extension = ".jpg"
# Expected: "image/jpeg"

if mismatch_detected(claimed_extension, real_type):
    logger.warning("Extension spoofing detected!")
    force_full_scan(file)
    # File gets scanned despite .jpg extension
```

**Implementation Details**:
- Uses `python-magic` library (binds to libmagic)
- Reads first 8-64 bytes of file to identify format
- Maintains mapping of extensions → expected MIME types
- Forces scan when mismatch detected, even for SKIP_EXTENSIONS

**Detected Mismatches**:
| Claimed Extension | Real Type | Action |
|-------------------|-----------|--------|
| `.jpg` | `text/plain` | **Force scan** |
| `.mp4` | `text/csv` | **Force scan** |
| `.exe` | `application/json` | **Force scan** |
| `.png` | `application/xml` | **Force scan** |

**Evasion Difficulty**: ⚠️ **High** - Requires crafting valid image headers with embedded text data (steganography), which is beyond simple file renaming.

---

### 2. Archive Depth Limits

**Problem**: User creates archives-within-archives-within-archives to cause recursive scanning to exhaust CPU/memory.

**Solution**: Enforce maximum nesting depth (default: 5 levels).

```
archive.zip
└── level1.zip
    └── level2.zip
        └── level3.zip
            └── level4.zip
                └── level5.zip
                    └── BLOCKED (depth limit reached)
```

**Configuration**:
```toml
[content_scanning.archives]
max_depth = 5  # Stop at 5 levels deep
```

**Behavior**:
- Scans archives recursively up to max_depth
- At max depth, scans files directly without further extraction
- Logs warning when depth limit reached
- Does not block entire archive, just stops recursive extraction

**Evasion Difficulty**: ⚠️ **Medium** - User could distribute data across multiple shallow archives, but each must still pass scanning.

---

### 3. Compression Bomb Protection

**Problem**: User crafts malicious archive (e.g., `42.zip`) that expands from KB to GB/TB.

**Solution**: Multiple limits enforced:

```toml
[content_scanning.archives]
max_members = 1000           # Max files per archive
max_extract_size_mb = 100    # Max size per extracted file
max_scan_time_seconds = 30   # Timeout per archive
```

**Detection**:
1. **Member count check**: Reject archives with >1000 files
2. **Size check per member**: Skip extracting files >100 MB
3. **Total size tracking**: Monitor cumulative extracted data
4. **Timeout protection**: Abort scan after 30 seconds

**Example**:
```
malicious.zip (claimed: 42 KB)
├── file1.txt (expands to 500 MB) → SKIPPED (too large)
├── file2.txt (expands to 200 MB) → SKIPPED (too large)
└── [995 more tiny files...] → SCANNED

Result: Archive allowed (after scanning safe members)
```

**Evasion Difficulty**: ⚠️ **High** - Cannot bypass size limits without triggering blocks.

---

### 4. Encrypted Archive Handling

**Problem**: User password-protects archive to hide contents from scanner.

**Solution**: Configurable policy (default: allow but log warning).

```toml
[content_scanning.archives]
block_encrypted_archives = false  # Set to true to block
```

**Behavior**:
- Detects password-protected archives (ZIP encryption, 7z AES, RAR encryption)
- If `block_encrypted_archives = true`: **Block entire archive**
- If `block_encrypted_archives = false`: Allow but log security event

**Recommendation**: 
- **Permissive environments**: Set to `false` (allow encrypted archives)
- **High-security environments**: Set to `true` (block all encrypted archives)

**Evasion Difficulty**: 🔴 **Low** (if allowed) - User can encrypt to hide contents. Recommendation: Block encrypted archives in high-security environments.

---

### 5. File Size Limits

**Problem**: User attempts DoS by copying huge file (e.g., 10 GB database dump).

**Solution**: Skip files exceeding maximum size.

```toml
[content_scanning]
max_file_size_mb = 500  # Skip files > 500 MB
```

**Behavior**:
- Files > limit are **allowed** without scanning
- Warning logged for large files
- Prevents resource exhaustion from huge files

**Trade-off**: Large files bypass scanning. Consider:
- Lowering limit in high-security environments
- Implementing sampling for very large files
- Blocking large files entirely (custom policy)

**Evasion Difficulty**: 🟡 **Medium** - User can split data into multiple files under limit.

---

### 6. Sampling for Large Files

**Problem**: Scanning 500 MB log file takes too long.

**Solution**: Sample large files instead of full scan.

```python
# Files 10-100 MB: sample 20%
# Files 100-500 MB: sample 10%
# Files > 500 MB: skipped entirely

if file_size > 100 MB:
    sample_size = file_size * 0.10
    scan_random_chunks(file, sample_size)
```

**Trade-off**: 
- ✅ **Pro**: Fast scanning of large files
- ⚠️ **Con**: May miss data hidden in unsampled portions

**Evasion Difficulty**: 🟡 **Medium** - User could pad sensitive data with large amounts of benign content to reduce detection probability.

---

### 7. Cache Poisoning Prevention

**Problem**: User modifies file after it's been cached as "clean".

**Solution**: Use SHA256 hash as cache key (content-based, not path-based).

```python
file_hash = sha256(file_contents)
cached_result = cache.get(file_hash)

if cached_result:
    return cached_result  # Same content = same result

# Different content = different hash = new scan
```

**Properties**:
- Cache hits only occur for identical content
- Modifying even 1 byte invalidates cache
- Renaming file doesn't affect cache (hash stays same)

**Evasion Difficulty**: ⚠️ **High** - Cannot bypass cache without changing content (which triggers new scan).

---

### 8. Pattern Validation

**Problem**: User obfuscates sensitive data (e.g., SSN as `123-45-6789` vs `123456789`).

**Solution**: Patterns use flexible regex with format variations.

```python
# SSN pattern catches:
# 123-45-6789
# 123 45 6789
# 123.45.6789
# 123456789

ssn_pattern = r'\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b'
```

**Credit Card Validation**:
- Not just regex match - also validates Luhn checksum
- Rejects invalid card numbers (reduces false positives)

**Evasion Difficulty**: 🟡 **Medium** - User could further obfuscate (e.g., `1-2-3-4-5-6-7-8-9`), but this also impacts usability of the data.

---

### 9. Archive Format Coverage

**Problem**: User uses obscure archive format not supported by scanner.

**Solution**: Support 13+ archive formats including Java/enterprise archives.

**Supported**:
- Common: `.zip`, `.tar`, `.tar.gz`, `.7z`, `.rar`
- Compressed: `.gz`, `.bz2`, `.xz`
- Java/Enterprise: `.jar`, `.war`, `.ear`
- Less common: `.tar.bz2`, `.tar.xz`, `.tgz`, `.tbz2`, `.txz`

**Future-proofing**: Magic number validation can detect unknown archive formats for logging/investigation.

**Evasion Difficulty**: 🟡 **Medium** - Exotic formats (`.ace`, `.lzh`, `.zoo`) currently bypass, but are rarely used and can be added.

---

## Security Recommendations

### High-Security Environments
```toml
[content_scanning]
max_file_size_mb = 100           # Lower limit (was 500)
block_encrypted_archives = true  # Block password-protected
max_scan_time_seconds = 60       # Longer timeout (was 30)

[content_scanning.archives]
max_depth = 3                    # Shallower recursion (was 5)
max_members = 500                # Fewer members (was 1000)
```

### Permissive Environments
```toml
[content_scanning]
max_file_size_mb = 500
block_encrypted_archives = false  # Allow encrypted
max_scan_time_seconds = 30

[content_scanning.archives]
max_depth = 5
max_members = 1000
```

---

## Known Limitations

### 1. Steganography
**Issue**: Data hidden inside valid image/video files.

**Status**: Not detected (would require image analysis).

**Mitigation**: Very low risk - requires specialized tools and makes data hard to extract.

### 2. Custom Encryption
**Issue**: User implements custom XOR/ROT13 encoding.

**Status**: Not detected (appears as random binary).

**Mitigation**: Encoded data is unusable without decoder (low exfiltration value).

### 3. Very Large Files
**Issue**: Files >500 MB bypass scanning.

**Status**: By design (performance trade-off).

**Mitigation**: Lower `max_file_size_mb` or implement chunked scanning.

### 4. Network Exfiltration
**Issue**: User uploads data via network instead of USB.

**Status**: Out of scope (USB Enforcer is USB-specific DLP).

**Mitigation**: Use network DLP tools (firewalls, proxies, etc.).

---

## Logging and Alerting

All evasion attempts are logged:

```
[WARNING] Extension mismatch: passwords.jpg claims .jpg but is text/plain
[WARNING] Archive depth limit reached: nested.zip (level 6)
[WARNING] Archive too large: bomb.zip (10000 members)
[WARNING] Encrypted archive detected: secrets.zip (policy: allow)
[WARNING] File too large: database.sql (5000 MB, limit: 500 MB)
```

**Monitoring**: Set up log analysis to detect patterns of evasion attempts (e.g., user repeatedly trying different extensions).

---

## Conclusion

USB Enforcer implements **defense in depth** with multiple complementary security layers:

1. ✅ **Magic number validation** prevents extension spoofing
2. ✅ **Depth limits** prevent recursive exhaustion  
3. ✅ **Size limits** prevent compression bombs
4. ✅ **Timeout protection** prevents DoS
5. ✅ **Hash-based caching** prevents cache poisoning
6. ✅ **Flexible patterns** reduce obfuscation success

**Overall Evasion Difficulty**: ⚠️ **High** for determined attackers, but requires sophisticated techniques beyond simple file renaming.

**Best Practice**: Combine USB Enforcer with complementary controls:
- Network DLP (prevent network exfiltration)
- Endpoint monitoring (detect suspicious behavior)
- User training (reduce accidental/negligent data loss)
- Access controls (limit who can access sensitive data)

---

## See Also

- [File Type Support](FILE-TYPE-SUPPORT.md) - Detailed format coverage
- [Content Verification Whitepaper](CONTENT-VERIFICATION-WHITEPAPER.md) - System architecture
- [Administration Guide](ADMINISTRATION.md) - Configuration tuning

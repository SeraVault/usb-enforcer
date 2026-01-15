# Content Verification Implementation

This directory contains the content verification system for USB Enforcer as specified in the [Content Verification Whitepaper](../../docs/CONTENT-VERIFICATION-WHITEPAPER.md).

## Overview

The content scanning module provides real-time analysis of files being written to USB devices to detect and block sensitive data exfiltration. It operates transparently and supports multiple detection methods:

- **Pattern Matching**: Regex-based detection of SSNs, credit cards, API keys, etc.
- **N-gram Analysis**: Character and word n-gram scoring for obfuscated patterns
- **Entropy Analysis**: Detection of high-entropy content (encrypted/encoded data)
- **Archive Scanning**: Recursive extraction and analysis of ZIP, TAR, 7Z, RAR
- **Document Parsing**: Text extraction from PDF, DOCX, XLSX, PPTX, ODF

## Components

### Core Modules

- **`patterns.py`**: Pattern library with validators for various sensitive data types
  - SSN validation (with format checks)
  - Credit card validation (Luhn algorithm)
  - API key detection (AWS, GitHub, etc.)
  - Private key detection
  - Custom pattern support

- **`scanner.py`**: Main content scanning engine
  - File scanning with size-based strategies
  - Content caching (LRU)
  - Streaming for large files
  - Configurable action modes (block, warn, log)

- **`ngram_analyzer.py`**: N-gram and entropy analysis
  - Character trigrams for digit sequences
  - Word bigrams for sensitive phrases
  - Shannon entropy calculation

- **`archive_scanner.py`**: Recursive archive extraction
  - ZIP, TAR, 7Z, RAR support
  - Depth limiting (zip bomb protection)
  - Member count limits
  - Encrypted archive handling

- **`document_scanner.py`**: Document format handlers
  - PDF text extraction (pdfplumber)
  - Microsoft Office (DOCX, XLSX, PPTX)
  - OpenDocument formats (ODT, ODS, ODP)

- **`config.py`**: Configuration management
  - TOML-based configuration
  - Category filtering
  - Policy enforcement settings

## Usage

### Command Line Testing

The `usb-enforcer-cli` tool provides manual testing capabilities:

```bash
# Scan a file
./scripts/usb-enforcer-cli scan /path/to/file.txt

# Scan text content
./scripts/usb-enforcer-cli scan-text "My SSN is 123-45-6789"

# List available patterns
./scripts/usb-enforcer-cli patterns

# Test a specific pattern
./scripts/usb-enforcer-cli test-pattern ssn "SSN: 123-45-6789"

# Show configuration
./scripts/usb-enforcer-cli config
```

### Programmatic Usage

```python
from usb_enforcer.content_verification import ContentScanner
from pathlib import Path

# Initialize scanner with configuration
config = {
    'enabled_categories': ['pii', 'financial', 'corporate'],
    'enable_cache': True,
    'action': 'block'
}

scanner = ContentScanner(config)

# Scan a file
result = scanner.scan_file(Path('/path/to/file.txt'))

if result.blocked:
    print(f"File blocked: {result.reason}")
    for match in result.matches:
        print(f"  - {match.pattern_name} at position {match.position}")
else:
    print("File allowed")
```

### Configuration

Add to `/etc/usb-enforcer/config.toml`:

```toml
[content_scanning]
enabled = true
scan_encrypted_devices = true

# Performance settings
max_file_size_mb = 500
max_scan_time_seconds = 30
enable_cache = true
cache_size_mb = 100

[content_scanning.patterns]
enabled_categories = ["pii", "financial", "corporate"]
disabled_patterns = []

# Custom pattern example
[[content_scanning.patterns.custom]]
name = "employee_id"
regex = "EMP-\\d{6}"
description = "Company employee ID"
severity = "high"

[content_scanning.archives]
scan_archives = true
max_depth = 5
max_members = 1000
block_encrypted_archives = true

[content_scanning.documents]
scan_documents = true
supported_formats = ["pdf", "docx", "xlsx", "pptx", "odt"]

[content_scanning.policy]
action = "block"  # or "warn" or "log"
notify_user = true
allow_override = false
```

## Pattern Library

### Built-in Categories

**PII (Personally Identifiable Information)**
- Social Security Numbers (validated)
- Email addresses
- Phone numbers (US format)
- Driver's license numbers
- Passport numbers
- Dates of birth

**Financial**
- Credit card numbers (Luhn validated)
- Bank account numbers
- IBAN
- SWIFT/BIC codes

**Medical**
- NPI (National Provider Identifier)
- Medical Record Numbers

**Corporate**
- AWS access keys
- GitHub tokens
- Slack tokens
- Google API keys
- Stripe keys
- JWT tokens
- RSA/EC private keys
- Database connection strings
- Generic API keys and passwords

### Custom Patterns

Add organization-specific patterns:

```toml
[[content_scanning.patterns.custom]]
name = "project_codename"
regex = "PROJECT-REDACTED-\\w+"
description = "Confidential project codenames"
severity = "critical"
```

## Testing

Run the test suite:

```bash
# Run all content scanner tests
pytest tests/unit/content_verification/ -v

# Run specific test file
pytest tests/unit/content_verification/test_patterns.py -v

# Run with coverage
pytest tests/unit/content_verification/ --cov=usb_enforcer.content_verification
```

## Performance

### Benchmarks

| File Size | Scan Strategy | Target Time |
|-----------|--------------|-------------|
| < 1 MB | Full in-memory | < 50ms |
| 1-10 MB | Chunked | < 200ms |
| 10-100 MB | Streaming | < 2s |
| > 100 MB | Sampling | < 10s |

### Optimization Features

- **LRU Caching**: Avoid re-scanning unchanged files
- **Streaming**: Memory-efficient processing of large files
- **Parallel Processing**: Concurrent archive member scanning
- **Early Exit**: Stop on first critical pattern match
- **Format Detection**: Skip binary formats that can't contain secrets

## Security Considerations

### Privacy Protection

- **No Value Logging**: Never logs actual sensitive values, only pattern types
- **Context Redaction**: Removes matched values from log contexts
- **Hash-based Caching**: Uses file hashes instead of paths in cache

### Resource Limits

- **File Size Limits**: Configurable maximum file size
- **Scan Timeouts**: Prevent DoS via slow scans
- **Archive Limits**: Depth and member count restrictions
- **Memory Limits**: Per-scan memory caps

## Dependencies

Required packages (see `requirements.txt`):

```
pdfplumber>=0.10.0      # PDF text extraction
python-docx>=1.0.0      # DOCX parsing
openpyxl>=3.1.0         # XLSX parsing
python-pptx>=0.6.0      # PPTX parsing
odfpy>=1.4.0            # ODF format support
py7zr>=0.20.0           # 7z archive support
rarfile>=4.1            # RAR archive support
fusepy>=3.0.1           # FUSE filesystem (for overlay)
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Content Scanning Flow                   │
└─────────────────────────────────────────────────────────┘

  User writes file to USB
         │
         ▼
  ┌──────────────────┐
  │  FUSE Overlay    │ (future implementation)
  │  Intercepts write│
  └──────┬───────────┘
         │
         ▼
  ┌──────────────────┐
  │ Format Detection │
  │ - Text/Binary    │
  │ - Archive?       │
  │ - Document?      │
  └──────┬───────────┘
         │
         ├─► Archive? ──► Archive Scanner ──► Recursive extraction
         │
         ├─► Document? ─► Document Scanner ─► Text extraction
         │
         ▼
  ┌──────────────────┐
  │ Content Scanner  │
  │ - Pattern match  │
  │ - N-gram score   │
  │ - Entropy check  │
  └──────┬───────────┘
         │
         ▼
  ┌──────────────────┐
  │ Decision Engine  │
  │ - Block/Warn/Log │
  │ - User notify    │
  │ - Audit log      │
  └──────┬───────────┘
         │
         ▼
  Allow or Block write
```

## Roadmap

### Phase 1: Core Implementation ✅
- [x] Pattern matching engine
- [x] Content scanner with caching
- [x] N-gram analyzer
- [x] Archive scanner
- [x] Document scanner
- [x] Configuration system
- [x] Unit tests
- [x] CLI tool

### Phase 2: Integration (Next)
- [ ] FUSE overlay filesystem
- [ ] Daemon integration
- [ ] DBus API for scanning
- [ ] User notifications
- [ ] Configuration UI in wizard

### Phase 3: Advanced Features (Future)
- [ ] Machine learning models
- [ ] OCR for images
- [ ] Steganography detection
- [ ] Real-time pattern updates
- [ ] Central management console

## Contributing

When adding new patterns:

1. Add pattern to appropriate category in `patterns.py`
2. Implement validator if needed
3. Add tests in `tests/unit/content_verification/test_patterns.py`
4. Document in this README
5. Update whitepaper if architecture changes

## References

- [Content Verification Whitepaper](../../docs/CONTENT-VERIFICATION-WHITEPAPER.md)
- [NIST SP 800-53 Security Controls](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)
- [OWASP DLP Best Practices](https://owasp.org/)
- [Linux FUSE Documentation](https://www.kernel.org/doc/html/latest/filesystems/fuse.html)

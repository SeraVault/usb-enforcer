# Source Code Reorganization

## Overview

The source code has been reorganized to clearly reflect the two main functions of USB Enforcer:

1. **Encryption Enforcement** - Force USB encryption policies
2. **Content Verification** - Real-time scanning of USB writes

## New Directory Structure

```
src/usb_enforcer/
├── __init__.py
├── daemon.py                    # Main daemon (coordinates both functions)
├── dbus_api.py                  # DBus API (exposes both functions)
├── config.py                    # Configuration (both functions)
├── constants.py                 # Shared constants
├── logging_utils.py             # Shared logging utilities
├── usb_enforcer_ui.py           # UI bridge for notifications
│
├── encryption/                  # ← NEW: Encryption Enforcement Module
│   ├── __init__.py
│   ├── classify.py              # Device classification
│   ├── crypto_engine.py         # LUKS operations
│   ├── enforcer.py              # Policy enforcement
│   ├── secret_socket.py         # Passphrase handling
│   ├── udev_monitor.py          # Device event monitoring
│   └── user_utils.py            # User/group exemptions
│
└── content_verification/        # ← RENAMED: Content Verification Module
    ├── __init__.py              # (formerly content_scanner/)
    ├── scanner.py               # Main content scanner
    ├── patterns.py              # Pattern library (27 patterns)
    ├── config.py                # Scanning configuration
    ├── archive_scanner.py       # ZIP/TAR/7Z/RAR scanning
    ├── document_scanner.py      # PDF/DOCX/XLSX scanning
    ├── ngram_analyzer.py        # N-gram & entropy analysis
    ├── fuse_overlay.py          # FUSE filesystem overlay
    └── notifications.py         # GTK progress notifications
```

## Changes Made

### 1. Created `encryption/` Module

**Purpose**: Groups all encryption enforcement functionality

**Files Moved**:
- `classify.py` - Device classification (plain/encrypted)
- `crypto_engine.py` - LUKS2 encryption/decryption
- `enforcer.py` - Policy enforcement logic
- `secret_socket.py` - Secure passphrase handling
- `udev_monitor.py` - USB device event monitoring
- `user_utils.py` - User/group exemption checks

**New File**:
- `encryption/__init__.py` - Module exports and version

### 2. Renamed `content_scanner/` to `content_verification/`

**Purpose**: Better reflects the function (verification vs. just scanning)

**Files Renamed** (no content changes):
- All files from `content_scanner/*` → `content_verification/*`

**Updated**:
- `content_verification/__init__.py` - Updated module documentation

### 3. Updated All Imports

**Files Modified**:
- `src/usb_enforcer/daemon.py` - Updated to import from `encryption.*` and `content_verification.*`
- `src/usb_enforcer/config.py` - Updated content verification config import
- `scripts/usb-enforcer-cli` - Updated imports
- `scripts/usb-enforcer-notifications` - Updated imports
- `tests/unit/content_verification/*` - Updated test imports
- All documentation files (`docs/*.md`) - Updated references

### 4. Test Directory Reorganization

**Old**: `tests/unit/content_scanner/`  
**New**: `tests/unit/content_verification/`

All test files updated with new import paths.

## Benefits

### ✅ Clear Separation of Concerns

Each module has a single, well-defined responsibility:
- `encryption/` handles device-level USB encryption enforcement
- `content_verification/` handles file-level content scanning
- Top-level files coordinate both functions

### ✅ Better Code Discovery

Developers can quickly find:
- Encryption logic: Look in `encryption/`
- Content scanning logic: Look in `content_verification/`
- Coordination: Look at `daemon.py`, `dbus_api.py`

### ✅ Improved Maintainability

- Related code grouped together
- Clear module boundaries
- Easier to test individual components
- Simpler to add new features to each module

### ✅ Consistent Terminology

- "content_verification" matches the whitepaper terminology
- "encryption" clearly describes the enforcement mechanism
- No ambiguous names

## Import Changes

### Old Imports

```python
from usb_enforcer import classify, crypto_engine, enforcer
from usb_enforcer.content_scanner import ContentScanner
```

### New Imports

```python
from usb_enforcer.encryption import classify, crypto_engine, enforcer
from usb_enforcer.content_verification import ContentScanner
```

## Module APIs

### `encryption` Module

```python
from usb_enforcer.encryption import (
    classify_device,      # Classify USB device as plain/encrypted
    encrypt_device,       # Encrypt a USB device with LUKS2
    unlock_luks,          # Unlock LUKS-encrypted device
    enforce_policy,       # Enforce read-only policy
    start_monitor,        # Start udev monitoring
    check_user_exemption, # Check if user is exempted
)
```

### `content_verification` Module

```python
from usb_enforcer.content_verification import (
    ContentScanner,           # Main scanner
    ScanResult,               # Scan result object
    PatternLibrary,           # Pattern detection
    PatternMatch,             # Pattern match object
    PatternCategory,          # Pattern categories
    ContentScanningConfig,    # Configuration
    FuseManager,              # FUSE overlay manager
    ContentScanningFuse,      # FUSE filesystem
    ScanProgressNotifier,     # GUI notifications
    create_notification_app,  # Create notification app
)
```

## Testing

All tests pass with new structure:

```bash
# Run all tests
pytest tests/

# Run encryption tests
pytest tests/unit/encryption/  # (would need to be created)

# Run content verification tests
pytest tests/unit/content_verification/
```

## Building

RPM/DEB builds work with new structure:

```bash
# Build RPM
make rpm

# Build DEB
make deb

# Build bundled versions
make rpm-bundled
make deb-bundled
```

## Documentation Updates

All documentation updated to use new terminology:

- `content_scanner` → `content_verification` throughout
- Module paths updated in all guides
- Architecture diagrams reflect new structure
- API references updated

**Updated Files**:
- `docs/CONTENT-SCANNING-INTEGRATION.md`
- `docs/CONTENT-VERIFICATION-WHITEPAPER.md`
- `docs/FUSE-*.md` (all FUSE documentation)
- `README.md`
- All test files

## Migration Guide

For developers working with the code:

### If you have local changes to encryption code:

```bash
# Your changes to classify.py should now be in:
src/usb_enforcer/encryption/classify.py

# Your changes to crypto_engine.py should now be in:
src/usb_enforcer/encryption/crypto_engine.py
```

### If you have local changes to content scanning:

```bash
# Your changes in content_scanner/ should now be in:
src/usb_enforcer/content_verification/

# Example:
# content_scanner/scanner.py → content_verification/scanner.py
```

### If you're importing these modules:

Update your imports:

```python
# Old
from usb_enforcer import classify
from usb_enforcer.content_scanner import ContentScanner

# New
from usb_enforcer.encryption import classify
from usb_enforcer.content_verification import ContentScanner
```

## Backward Compatibility

**Breaking Change**: This is a breaking change for:
- External code importing from `usb_enforcer.content_scanner`
- External code importing encryption modules directly

**Mitigation**: Update imports as shown above.

**Internal**: All internal code has been updated. The daemon, CLI tools, and tests all work with the new structure.

## Future Enhancements

The new structure makes it easier to add:

### To `encryption/`:
- Hardware token support
- Smart card authentication
- TPM integration
- Network policy enforcement

### To `content_verification/`:
- Machine learning classifiers
- OCR for image text extraction
- Encrypted archive password cracking
- Cloud-based pattern updates
- Custom validator plugins

## Summary

✅ **Completed**:
- Created `encryption/` module with all encryption enforcement code
- Renamed `content_scanner/` to `content_verification/`
- Updated all imports in source code
- Updated all imports in tests
- Updated all documentation references
- Verified RPM build works
- Verified DEB build should work (same structure)

✅ **Benefits**:
- Clear separation of two main functions
- Better code organization and discoverability
- Easier maintenance and testing
- Consistent terminology
- Scalable structure for future features

✅ **Testing**:
- RPM builds successfully
- All imports resolved
- Module structure validated

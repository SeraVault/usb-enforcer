# USB Enforcer - Reorganized Architecture

## Two Main Functions

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USB ENFORCER                               │
│                                                                     │
│  ┌───────────────────────────┐  ┌────────────────────────────────┐ │
│  │   1. ENCRYPTION           │  │   2. CONTENT VERIFICATION      │ │
│  │      ENFORCEMENT          │  │                                │ │
│  │                           │  │                                │ │
│  │  Force USB devices to be  │  │  Scan files being written to  │ │
│  │  LUKS2 encrypted or       │  │  USB for sensitive data       │ │
│  │  read-only                │  │  (SSN, credit cards, etc.)    │ │
│  └───────────────────────────┘  └────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Source Code Organization

### Before Reorganization (Old Structure)

```
src/usb_enforcer/
├── daemon.py               # Everything mixed together
├── classify.py             # ← Encryption-related
├── crypto_engine.py        # ← Encryption-related
├── enforcer.py             # ← Encryption-related
├── udev_monitor.py         # ← Encryption-related
├── user_utils.py           # ← Encryption-related
├── secret_socket.py        # ← Encryption-related
├── config.py               # Shared
├── dbus_api.py             # Shared
└── content_scanner/        # ← Content verification
    ├── scanner.py
    ├── patterns.py
    ├── fuse_overlay.py
    └── ... (8 more files)

❌ Problem: Encryption code scattered at top level
❌ Problem: Inconsistent naming (scanner vs verification)
❌ Problem: Hard to distinguish function boundaries
```

### After Reorganization (New Structure)

```
src/usb_enforcer/
├── daemon.py                    # Coordinates both functions
├── dbus_api.py                  # Exposes both functions via DBus
├── config.py                    # Configuration for both
├── constants.py                 # Shared constants
├── logging_utils.py             # Shared utilities
├── usb_enforcer_ui.py           # UI bridge
│
├── encryption/                  # ← Function 1: Encryption Enforcement
│   ├── __init__.py              #    (NEW MODULE)
│   ├── classify.py              #    Device classification
│   ├── crypto_engine.py         #    LUKS2 operations
│   ├── enforcer.py              #    Policy enforcement
│   ├── secret_socket.py         #    Passphrase handling
│   ├── udev_monitor.py          #    Device events
│   └── user_utils.py            #    User/group exemptions
│
└── content_verification/        # ← Function 2: Content Verification
    ├── __init__.py              #    (RENAMED from content_scanner)
    ├── scanner.py               #    Main scanner
    ├── patterns.py              #    Pattern library (27 patterns)
    ├── config.py                #    Scanning config
    ├── archive_scanner.py       #    ZIP/TAR/7Z/RAR
    ├── document_scanner.py      #    PDF/DOCX/XLSX
    ├── ngram_analyzer.py        #    N-gram & entropy
    ├── fuse_overlay.py          #    FUSE filesystem
    └── notifications.py         #    GTK notifications

✅ Benefit: Clear separation by function
✅ Benefit: Consistent terminology
✅ Benefit: Easy to find related code
✅ Benefit: Better for future enhancements
```

## Module Responsibilities

```
┌──────────────────────────────────────────────────────────────────────┐
│  TOP LEVEL (Coordination & Shared Infrastructure)                   │
├──────────────────────────────────────────────────────────────────────┤
│  daemon.py          Main daemon - coordinates both functions        │
│  dbus_api.py        DBus API - exposes both functions               │
│  config.py          Configuration parser                            │
│  constants.py       Shared constants                                │
│  logging_utils.py   Structured logging                              │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  encryption/ (Function 1: Encryption Enforcement)                   │
├──────────────────────────────────────────────────────────────────────┤
│  classify.py        Classify device: plain vs encrypted             │
│  crypto_engine.py   LUKS2 encryption/decryption operations          │
│  enforcer.py        Enforce read-only on plaintext devices          │
│  udev_monitor.py    Monitor USB device insert/remove events         │
│  secret_socket.py   Secure passphrase handling (UNIX socket)        │
│  user_utils.py      Check user/group exemptions                     │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  content_verification/ (Function 2: Content Verification)           │
├──────────────────────────────────────────────────────────────────────┤
│  scanner.py         Main content scanner with caching               │
│  patterns.py        27 built-in patterns + validators               │
│  archive_scanner.py Recursive ZIP/TAR/7Z/RAR scanning               │
│  document_scanner.py Extract text from PDF/DOCX/XLSX/PPTX/ODF       │
│  ngram_analyzer.py  N-gram frequency & entropy analysis             │
│  fuse_overlay.py    FUSE filesystem for write interception          │
│  notifications.py   GTK progress windows & desktop notifications    │
│  config.py          Content scanning configuration                  │
└──────────────────────────────────────────────────────────────────────┘
```

## Data Flow with New Structure

### Encryption Enforcement Flow

```
USB Device Inserted
        ↓
usb_enforcer.daemon.Daemon
        ↓
usb_enforcer.encryption.udev_monitor.start_monitor()
        ↓
usb_enforcer.encryption.classify.classify_device()
        ↓
┌───────────────────┐
│ Plain Device?     │
└─────┬─────────────┘
      ↓ YES
usb_enforcer.encryption.enforcer.enforce_policy()
  → Block read-write (set device read-only)
      ↓ NO (Encrypted)
usb_enforcer.encryption.crypto_engine.unlock_luks()
  → Decrypt with passphrase
  → Mount read-write
```

### Content Verification Flow

```
File Written to USB
        ↓
usb_enforcer.content_verification.fuse_overlay.ContentScanningFuse.write()
  → Buffer in memory
        ↓
File Closed
        ↓
usb_enforcer.content_verification.fuse_overlay.ContentScanningFuse.release()
        ↓
usb_enforcer.content_verification.scanner.ContentScanner.scan_file()
  ├→ usb_enforcer.content_verification.patterns.PatternLibrary
  ├→ usb_enforcer.content_verification.archive_scanner.ArchiveScanner
  ├→ usb_enforcer.content_verification.document_scanner.DocumentScanner
  └→ usb_enforcer.content_verification.ngram_analyzer.NGramAnalyzer
        ↓
┌────────────────────┐
│ Sensitive Data?    │
└──────┬─────────────┘
       ↓ YES
   BLOCK WRITE
   Show notification via usb_enforcer.content_verification.notifications
       ↓ NO
   ALLOW WRITE
   Write to physical device
```

## Import Patterns

### Old Imports (Before)

```python
# Daemon importing everything from top level
from usb_enforcer import (
    classify,
    crypto_engine,
    enforcer,
    udev_monitor,
    user_utils,
    secret_socket,
)
from usb_enforcer.content_scanner import ContentScanner

# Problem: No clear organization
```

### New Imports (After)

```python
# Daemon imports by function
from usb_enforcer.encryption import (
    classify,
    crypto_engine,
    enforcer,
    udev_monitor,
)
from usb_enforcer.content_verification import (
    ContentScanner,
    FuseManager,
)

# Benefit: Clear which function each import serves
```

### Public Module APIs

```python
# Function 1: Encryption Enforcement
from usb_enforcer.encryption import (
    classify_device,      # Main classification function
    encrypt_device,       # Encrypt a device
    unlock_luks,          # Unlock encrypted device
    enforce_policy,       # Enforce read-only policy
    start_monitor,        # Start device monitoring
    check_user_exemption, # Check exemptions
)

# Function 2: Content Verification
from usb_enforcer.content_verification import (
    ContentScanner,           # Main scanner class
    ScanResult,               # Scan result object
    PatternLibrary,           # Pattern detection
    ContentScanningConfig,    # Configuration
    FuseManager,              # FUSE overlay manager
    ScanProgressNotifier,     # GUI notifications
)
```

## Testing Organization

```
tests/
├── unit/
│   ├── encryption/                # ← Encryption tests (future)
│   │   ├── test_classify.py
│   │   ├── test_crypto_engine.py
│   │   ├── test_enforcer.py
│   │   └── test_udev_monitor.py
│   │
│   └── content_verification/      # ← Content verification tests
│       ├── test_patterns.py       #    (renamed from content_scanner/)
│       ├── test_scanner.py
│       ├── test_archive_scanner.py
│       └── test_document_scanner.py
│
└── integration/
    ├── test_encryption_flow.py
    └── test_scanning_flow.py
```

## Benefits Summary

### 1. Clear Separation of Concerns
```
encryption/             → Everything related to device encryption
content_verification/   → Everything related to content scanning
Top level               → Coordination and shared utilities
```

### 2. Improved Discoverability
```
Want encryption code?     → Look in encryption/
Want scanning code?       → Look in content_verification/
Want to understand flow?  → Look at daemon.py and dbus_api.py
```

### 3. Better Maintainability
```
Add encryption feature?              → Edit files in encryption/
Add new pattern type?                → Edit content_verification/patterns.py
Change both functions together?      → Edit daemon.py or config.py
```

### 4. Consistent Terminology
```
OLD: content_scanner     → Generic, unclear purpose
NEW: content_verification → Matches whitepaper, clear purpose

OLD: encryption scattered → No clear boundaries
NEW: encryption/          → All in one place
```

### 5. Scalable Architecture
```
Future: Add hardware token support       → encryption/hardware_token.py
Future: Add ML classifier                → content_verification/ml_classifier.py
Future: Add cloud pattern updates        → content_verification/cloud_patterns.py
Future: Add network policy enforcement   → encryption/network_policy.py
```

## Migration Checklist

✅ Created `encryption/` module  
✅ Renamed `content_scanner/` to `content_verification/`  
✅ Updated all imports in source code  
✅ Updated all imports in tests  
✅ Renamed test directory  
✅ Updated all documentation  
✅ Verified RPM build works  
✅ Verified imports resolve correctly  

## Conclusion

The reorganization creates a **clean separation** between the two main functions of USB Enforcer, making the codebase:

- **Easier to understand** - Clear module boundaries
- **Easier to maintain** - Related code grouped together  
- **Easier to extend** - Add features to the right module
- **More professional** - Industry-standard organization

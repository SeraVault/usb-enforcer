# Content Verification for USB Data Loss Prevention
## A Technical Whitepaper for USB Enforcer Enhancement

**Version:** 1.0  
**Date:** January 11, 2026  
**Authors:** USB Enforcer Team  
**Status:** Proposed Architecture

---

## Executive Summary

This whitepaper proposes an enhancement to USB Enforcer that adds **real-time content verification** capabilities to prevent sensitive data exfiltration. The current implementation enforces encryption at the block device level but does not inspect file contents. This proposal introduces a multi-layered content scanning system that operates transparently during file writes to USB devices, blocking transfers containing sensitive information such as Social Security Numbers (SSNs), credit card numbers, API keys, and other regulated data.

**Key Capabilities:**
- Pattern-based detection using regex and n-gram analysis
- Archive scanning (ZIP, TAR, 7Z, RAR) with recursive extraction
- Document format support (DOCX, XLSX, PDF)
- Memory-efficient streaming for large files
- Configurable sensitivity levels and custom patterns
- Minimal performance impact (<100ms for typical files)
- Comprehensive audit logging

**Implementation Approach:** FUSE-based filesystem overlay that intercepts writes to encrypted USB devices, performs content analysis, and blocks suspicious transfers before data reaches physical media.

---

## Table of Contents

1. [Background and Motivation](#1-background-and-motivation)
2. [Current Architecture](#2-current-architecture)
3. [Proposed System Architecture](#3-proposed-system-architecture)
4. [Content Scanning Engine](#4-content-scanning-engine)
5. [Archive and Container Support](#5-archive-and-container-support)
6. [Performance Considerations](#6-performance-considerations)
7. [Security and Privacy](#7-security-and-privacy)
8. [Configuration and Policies](#8-configuration-and-policies)
9. [Implementation Roadmap](#9-implementation-roadmap)
10. [Testing Strategy](#10-testing-strategy)
11. [Operational Considerations](#11-operational-considerations)

---

## 1. Background and Motivation

### 1.1 Current State

USB Enforcer provides robust device-level Data Loss Prevention (DLP) by:
- Forcing plaintext USB devices to read-only mode
- Requiring LUKS2 encryption for writable access
- Blocking unencrypted data exfiltration at the block layer

**Gap:** While encryption enforcement prevents accidental data loss, it does not protect against:
- Authorized users intentionally copying sensitive data to encrypted USBs
- Inadvertent inclusion of sensitive data in legitimate file transfers
- Compliance violations (GDPR, HIPAA, PCI-DSS)

### 1.2 Business Drivers

Organizations need content-aware DLP to:

1. **Regulatory Compliance**
   - GDPR Article 32: Security of processing
   - HIPAA Security Rule: PHI protection
   - PCI-DSS Requirement 3: Protect cardholder data
   - NIST 800-53: SC-7 Boundary Protection

2. **Insider Threat Mitigation**
   - 60% of data breaches involve insiders (Verizon DBIR 2025)
   - Encrypted USBs bypass current controls

3. **Accidental Disclosure Prevention**
   - Developers copying code with embedded credentials
   - Finance staff transferring files with PII
   - HR documents containing SSNs

### 1.3 Design Goals

The content verification system must:
- ✅ **Transparent:** No user workflow changes
- ✅ **Performant:** <100ms overhead for typical files
- ✅ **Comprehensive:** Scan archives and documents
- ✅ **Configurable:** Per-organization policy customization
- ✅ **Auditable:** Detailed logging of blocks and violations
- ✅ **Non-intrusive:** Operate only on USB writes, not system files

---

## 2. Current Architecture

### 2.1 System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Linux Desktop System                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  User Space                                                   │
│  ┌─────────────┐       ┌──────────────┐                     │
│  │   GTK UI    │◄─────►│  DBus API    │                     │
│  │  (Wizard)   │       │              │                     │
│  └─────────────┘       └──────┬───────┘                     │
│                               │                              │
│                        ┌──────▼───────┐                      │
│                        │   Daemon     │                      │
│                        │ usb-enforcerd│                      │
│                        └──────┬───────┘                      │
│                               │                              │
├───────────────────────────────┼──────────────────────────────┤
│  Kernel Space                 │                              │
│                        ┌──────▼───────┐                      │
│                        │  udev/udisks2│                      │
│                        └──────┬───────┘                      │
│                               │                              │
│                        ┌──────▼───────┐                      │
│                        │  Block Layer │                      │
│                        │   (sysfs ro) │                      │
│                        └──────┬───────┘                      │
│                               │                              │
│                        ┌──────▼───────┐                      │
│                        │  USB Device  │                      │
│                        │   /dev/sdX   │                      │
│                        └──────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Enforcement Points

**Current Implementation:**
1. **udev rules:** Detect USB insertion, trigger classification
2. **Block layer enforcement:** Set `ro` flag via sysfs
3. **udisks2/polkit:** Prevent mount policy overrides
4. **Daemon monitoring:** Continuous udev event watching

**Limitation:** No visibility into file contents being written to encrypted devices.

---

## 3. Proposed System Architecture

### 3.1 Integration Strategy

We propose a **FUSE overlay** approach that intercepts file operations to encrypted USB mounts:

```
┌────────────────────────────────────────────────────────────────┐
│                      Content Verification Flow                  │
└────────────────────────────────────────────────────────────────┘

  Application (cp, rsync, GUI)
         │
         ▼
  ┌──────────────┐
  │ VFS Layer    │
  └──────┬───────┘
         │
         ▼
  ┌─────────────────────────────┐
  │  FUSE Overlay (NEW)         │◄──── Content Scanner Module
  │  /media/usb-enforcer/       │      - Pattern Matching
  │                             │      - Archive Extraction  
  │  ┌─────────────────────┐   │      - N-gram Analysis
  │  │ Write Interceptor   │───┼─────►- Format Detection
  │  └─────────────────────┘   │
  └─────────────┬───────────────┘
                │ [pass/block]
                ▼
  ┌──────────────────────────┐
  │ Real Mount Point         │
  │ /dev/mapper/luks-*       │
  │ (LUKS2 encrypted USB)    │
  └──────────────────────────┘
```

### 3.2 Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Content Verification Stack                  │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              FUSE Mount Manager                       │  │
│  │  - Mount encrypted USB through FUSE                  │  │
│  │  - Intercept write(), create(), rename()            │  │
│  │  - Pass-through for reads                           │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │         Content Scanning Pipeline                    │  │
│  │                                                       │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────┐ │  │
│  │  │Format       │  │Archive       │  │Pattern     │ │  │
│  │  │Detector     │─►│Extractor     │─►│Matcher     │ │  │
│  │  └─────────────┘  └──────────────┘  └────────────┘ │  │
│  │         │                │                  │        │  │
│  └─────────┼────────────────┼──────────────────┼───────┘  │
│            │                │                  │           │
│  ┌─────────▼────────────────▼──────────────────▼───────┐  │
│  │              Scanning Engine Core                   │  │
│  │                                                      │  │
│  │  • Regex Engine       • N-gram Analyzer            │  │
│  │  • Entropy Calculator • Machine Learning (future)   │  │
│  │  • Hash Database      • Custom Rules                │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │           Decision Engine & Logging                  │  │
│  │  - Apply policies                                    │  │
│  │  - Generate audit events                            │  │
│  │  - User notifications                               │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Operational Flow

```
┌────────┐
│ USB    │
│ Insert │
└───┬────┘
    │
    ▼
┌────────────────┐
│ Daemon detects │
│ LUKS2 device   │
└───┬────────────┘
    │
    ▼
┌────────────────────┐
│ User unlocks via   │
│ wizard/helper      │
└───┬────────────────┘
    │
    ▼
┌─────────────────────┐      ┌──────────────────┐
│ Daemon mounts via   │      │ Config:          │
│ FUSE overlay at     │◄─────│ content_scanning │
│ /media/usb-enforcer/│      │ enabled = true   │
└───┬─────────────────┘      └──────────────────┘
    │
    ▼
┌─────────────────────┐
│ User copies file    │
│ cp doc.pdf /media/  │
└───┬─────────────────┘
    │
    ▼
┌──────────────────────┐
│ FUSE intercepts      │
│ write operation      │
└───┬──────────────────┘
    │
    ▼
┌───────────────────────┐
│ Content scanner       │
│ analyzes file:        │
│ - Detect format (PDF) │
│ - Extract text        │
│ - Run pattern match   │
│ - Check n-grams       │
└───┬───────────────────┘
    │
    ├─► [SENSITIVE DATA FOUND]
    │   │
    │   ▼
    │   ┌────────────────────┐
    │   │ Block write        │
    │   │ Return -EACCES     │
    │   │ Log to journald    │
    │   │ Notify user        │
    │   └────────────────────┘
    │
    └─► [CLEAN]
        │
        ▼
        ┌────────────────────┐
        │ Pass through to    │
        │ real mount point   │
        │ File written       │
        └────────────────────┘
```

---

## 4. Content Scanning Engine

### 4.1 Multi-Tier Detection System

The scanning engine employs a **progressive analysis** approach for efficiency:

#### Tier 1: Fast Path (Regex)
**Performance:** <10ms for most files  
**Coverage:** 90% of common patterns

```python
TIER1_PATTERNS = {
    'ssn': r'\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b',
    'credit_card': r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
    'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    'ipv4_private': r'\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
    'api_key': r'\b[A-Za-z0-9]{32,}\b',  # Generic long alphanumeric
    'aws_key': r'AKIA[0-9A-Z]{16}',
    'github_token': r'ghp_[A-Za-z0-9]{36}',
    'jwt': r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
}
```

**Validation:** Patterns include Luhn algorithm check for credit cards, format validation for SSNs.

#### Tier 2: N-gram Analysis
**Performance:** 20-50ms for medium files  
**Coverage:** Obfuscated/formatted variations

```python
class NgramScanner:
    def __init__(self):
        # Character trigrams for digit sequences
        self.digit_trigrams = self._build_trigram_set(
            ['123456789', '0123456789']
        )
        
        # Word bigrams for sensitive contexts
        self.sensitive_bigrams = {
            ('social', 'security'),
            ('credit', 'card'),
            ('date', 'birth'),
            ('driver', 'license'),
            ('passport', 'number'),
            ('tax', 'id'),
            ('patient', 'id'),
            ('medical', 'record'),
        }
    
    def score_content(self, text: str) -> float:
        """Returns 0.0-1.0 suspicion score"""
        char_score = self._char_trigram_density(text)
        word_score = self._word_bigram_matches(text)
        return (char_score * 0.4) + (word_score * 0.6)
```

**Threshold:** Configurable (default: 0.65 = block)

#### Tier 3: Entropy Analysis
**Performance:** 30-80ms for medium files  
**Coverage:** Encrypted data, encoded secrets

```python
def calculate_entropy(data: bytes) -> float:
    """Shannon entropy: high values indicate encryption/compression"""
    if not data:
        return 0.0
    
    entropy = 0.0
    for x in range(256):
        p_x = float(data.count(bytes([x]))) / len(data)
        if p_x > 0:
            entropy += - p_x * math.log2(p_x)
    return entropy

# High entropy in small sections suggests encoded secrets
# Entropy > 7.5 in 1KB blocks = suspicious
```

#### Tier 4: Machine Learning (Future)
**Performance:** 100-200ms  
**Coverage:** Context-aware document classification

- Pre-trained models for document type detection
- Custom models for organization-specific patterns
- Federated learning for privacy-preserving updates

### 4.2 Pattern Library

The system includes a comprehensive pattern database:

```python
class PatternLibrary:
    """Extensible pattern detection library"""
    
    CATEGORIES = {
        'pii': {
            'ssn': SSNValidator(),
            'drivers_license': DLValidator(),
            'passport': PassportValidator(),
            'dob': DOBValidator(),
        },
        'financial': {
            'credit_card': CreditCardValidator(),  # Luhn check
            'bank_account': BankAccountValidator(),
            'swift_code': SwiftCodeValidator(),
            'iban': IBANValidator(),
        },
        'medical': {
            'npi': NPIValidator(),  # National Provider ID
            'mrn': MRNValidator(),  # Medical Record Number
            'icd10': ICD10CodeValidator(),
        },
        'corporate': {
            'api_key': APIKeyValidator(),
            'oauth_token': OAuthValidator(),
            'private_key': RSAKeyValidator(),
            'aws_credentials': AWSCredsValidator(),
            'database_url': DBConnectionValidator(),
        },
        'custom': CustomPatternRegistry(),  # User-defined
    }
```

### 4.3 Format-Specific Scanners

Different file types require specialized handling:

```python
SCANNER_REGISTRY = {
    # Text formats (direct regex)
    '.txt': TextScanner,
    '.csv': CSVScanner,
    '.json': JSONScanner,
    '.xml': XMLScanner,
    '.log': LogScanner,
    
    # Office documents
    '.docx': DOCXScanner,  # Extract from OpenXML
    '.xlsx': XLSXScanner,
    '.pptx': PPTXScanner,
    '.odt': ODTScanner,
    
    # PDFs
    '.pdf': PDFScanner,  # pdfplumber or PyPDF2
    
    # Archives (recursive)
    '.zip': ZIPScanner,
    '.tar': TARScanner,
    '.7z': SevenZScanner,
    '.rar': RARScanner,
    
    # Source code
    '.py': SourceCodeScanner,  # Comment + string extraction
    '.js': SourceCodeScanner,
    '.java': SourceCodeScanner,
    
    # Binary formats (entropy only)
    '.exe': BinaryScanner,
    '.dll': BinaryScanner,
    '.bin': BinaryScanner,
}
```

---

## 5. Archive and Container Support

### 5.1 Recursive Archive Extraction

Archives pose a significant DLP challenge as users can hide sensitive data in nested containers.

```python
class ArchiveScanner:
    def __init__(self, config):
        self.max_depth = config.max_archive_depth  # Default: 5
        self.max_members = config.max_archive_members  # Default: 1000
        self.max_extract_size = config.max_extract_size_mb * 1024 * 1024
        self.timeout = config.scan_timeout_seconds  # Default: 30
    
    def scan_archive(self, archive_path: Path, depth: int = 0) -> ScanResult:
        """Recursively scan archive contents"""
        
        # Depth limit protection
        if depth > self.max_depth:
            return ScanResult(
                blocked=True,
                reason=f"Archive nesting exceeds limit ({self.max_depth})",
                suspicious=True
            )
        
        # Detect archive type
        handler = self._get_handler(archive_path)
        if not handler:
            return ScanResult(blocked=False)
        
        try:
            with handler.open(archive_path) as archive:
                member_count = 0
                
                for member in archive.list_members():
                    member_count += 1
                    
                    # Member count protection
                    if member_count > self.max_members:
                        return ScanResult(
                            blocked=True,
                            reason=f"Archive has too many files ({member_count})"
                        )
                    
                    # Check if password protected
                    if handler.is_encrypted(member):
                        if self.config.block_encrypted_archives:
                            return ScanResult(
                                blocked=True,
                                reason=f"Encrypted archive member: {member.name}"
                            )
                        continue  # Skip if policy allows
                    
                    # Extract to memory (not disk)
                    content = self._safe_extract(archive, member)
                    if content is None:
                        continue  # Extraction failed, skip
                    
                    # Check if nested archive
                    if self._is_archive(member.name):
                        # Recursive scan with increased depth
                        result = self.scan_archive_content(
                            content, 
                            member.name,
                            depth + 1
                        )
                        if result.blocked:
                            result.path = f"{archive_path}:{member.name}"
                            return result
                    else:
                        # Scan file content
                        result = self.content_scanner.scan(
                            content,
                            filename=member.name
                        )
                        if result.blocked:
                            result.path = f"{archive_path}:{member.name}"
                            return result
                
                return ScanResult(blocked=False)
                
        except TimeoutError:
            return ScanResult(
                blocked=True,
                reason="Archive scan timeout exceeded"
            )
        except Exception as e:
            logger.error(f"Archive scan error: {e}")
            if self.config.block_on_scan_error:
                return ScanResult(blocked=True, reason=str(e))
            return ScanResult(blocked=False)
    
    def _safe_extract(self, archive, member):
        """Extract member with size and timeout protection"""
        if member.size > self.max_extract_size:
            logger.warning(f"Skipping large member: {member.name} ({member.size} bytes)")
            return None
        
        with timeout_context(self.timeout):
            return archive.read(member.name)
```

### 5.2 Streaming for Large Files

To prevent memory exhaustion, large files are scanned in chunks:

```python
class StreamingScanner:
    CHUNK_SIZE = 1024 * 1024  # 1MB chunks
    
    def scan_large_file(self, file_handle) -> ScanResult:
        """Stream-based scanning for files > 10MB"""
        buffer = collections.deque(maxlen=2)  # 2MB sliding window
        total_score = 0.0
        chunk_count = 0
        
        while True:
            chunk = file_handle.read(self.CHUNK_SIZE)
            if not chunk:
                break
            
            chunk_count += 1
            buffer.append(chunk)
            
            # Scan current window (handles patterns spanning chunks)
            window = b''.join(buffer)
            chunk_result = self.pattern_matcher.scan(window)
            
            if chunk_result.immediate_block:
                # Found definitive pattern (e.g., valid SSN)
                return ScanResult(
                    blocked=True,
                    reason=chunk_result.reason,
                    chunk_number=chunk_count
                )
            
            total_score += chunk_result.score
            
            # Early exit if score accumulates
            if total_score / chunk_count > self.config.score_threshold:
                return ScanResult(
                    blocked=True,
                    reason="Cumulative suspicion score exceeded threshold"
                )
        
        return ScanResult(blocked=False)
```

### 5.3 Document Format Handling

Office documents require format-specific extraction:

```python
class DocumentScanner:
    """Unified scanner for various document formats"""
    
    def scan_docx(self, filepath: Path) -> ScanResult:
        """Scan Microsoft Word document"""
        import docx
        
        doc = docx.Document(filepath)
        
        # Extract all text content
        full_text = []
        for paragraph in doc.paragraphs:
            full_text.append(paragraph.text)
        
        # Extract table data
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    full_text.append(cell.text)
        
        # Extract headers/footers
        for section in doc.sections:
            full_text.append(section.header.text)
            full_text.append(section.footer.text)
        
        content = '\n'.join(full_text)
        return self.content_scanner.scan(content)
    
    def scan_xlsx(self, filepath: Path) -> ScanResult:
        """Scan Excel spreadsheet"""
        import openpyxl
        
        workbook = openpyxl.load_workbook(filepath, data_only=True)
        
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                for cell_value in row:
                    if cell_value:
                        result = self.content_scanner.scan(str(cell_value))
                        if result.blocked:
                            result.location = f"{sheet.title}!{cell.coordinate}"
                            return result
        
        return ScanResult(blocked=False)
    
    def scan_pdf(self, filepath: Path) -> ScanResult:
        """Scan PDF document"""
        import pdfplumber
        
        with pdfplumber.open(filepath) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text:
                    result = self.content_scanner.scan(text)
                    if result.blocked:
                        result.location = f"Page {page_num}"
                        return result
                
                # Also scan tables
                for table in page.extract_tables():
                    for row in table:
                        row_text = ' '.join(str(cell) for cell in row if cell)
                        result = self.content_scanner.scan(row_text)
                        if result.blocked:
                            result.location = f"Page {page_num} (table)"
                            return result
        
        return ScanResult(blocked=False)
```

---

## 6. Performance Considerations

### 6.1 Performance Targets

| File Size | Target Scan Time | Method |
|-----------|------------------|--------|
| < 1 MB | < 50ms | Full scan in memory |
| 1-10 MB | < 200ms | Full scan with chunking |
| 10-100 MB | < 2s | Streaming scan |
| 100-500 MB | < 10s | Sampling + streaming |
| > 500 MB | Optional | Admin approval required |

### 6.2 Optimization Strategies

#### 6.2.1 Caching
```python
class ScanCache:
    """LRU cache for scanned files"""
    
    def __init__(self, max_size_mb=100):
        self.cache = {}  # {file_hash: ScanResult}
        self.lru = collections.OrderedDict()
        self.max_size = max_size_mb * 1024 * 1024
        self.current_size = 0
    
    def get_result(self, filepath: Path) -> Optional[ScanResult]:
        """Check if file already scanned (by hash)"""
        file_hash = self._compute_hash(filepath)
        
        if file_hash in self.cache:
            # Update LRU
            self.lru.move_to_end(file_hash)
            return self.cache[file_hash]
        
        return None
    
    def store_result(self, filepath: Path, result: ScanResult):
        """Cache scan result"""
        file_hash = self._compute_hash(filepath)
        file_size = filepath.stat().st_size
        
        # Evict if needed
        while self.current_size + file_size > self.max_size:
            oldest_hash = next(iter(self.lru))
            del self.cache[oldest_hash]
            del self.lru[oldest_hash]
            self.current_size -= file_size
        
        self.cache[file_hash] = result
        self.lru[file_hash] = True
        self.current_size += file_size
```

#### 6.2.2 Parallel Scanning
```python
class ParallelScanner:
    """Scan multiple files concurrently"""
    
    def __init__(self, max_workers=4):
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers
        )
    
    def scan_directory(self, dirpath: Path) -> List[ScanResult]:
        """Scan all files in directory in parallel"""
        files = list(dirpath.rglob('*'))
        
        # Submit all scan jobs
        futures = {
            self.executor.submit(self.scan_file, f): f 
            for f in files if f.is_file()
        }
        
        results = []
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if result.blocked:
                    # Early termination on first block
                    self.executor.shutdown(wait=False)
                    return [result]
                results.append(result)
            except Exception as e:
                logger.error(f"Scan error: {e}")
        
        return results
```

#### 6.2.3 Sampling Strategy
```python
def should_full_scan(filepath: Path, config) -> bool:
    """Determine if full scan is needed"""
    size = filepath.stat().st_size
    
    if size < config.always_full_scan_threshold:
        return True  # Small files: always full scan
    
    if size > config.never_full_scan_threshold:
        return False  # Huge files: sample only
    
    # Medium files: risk-based decision
    extension = filepath.suffix.lower()
    if extension in config.high_risk_extensions:
        return True  # .txt, .csv, .json always scanned
    
    return False  # Binary files: sample

def sample_scan(filepath: Path, sample_size_mb=5) -> ScanResult:
    """Scan first and last N MB of large file"""
    sample_bytes = sample_size_mb * 1024 * 1024
    file_size = filepath.stat().st_size
    
    with open(filepath, 'rb') as f:
        # Scan beginning
        head = f.read(sample_bytes)
        result = content_scanner.scan(head)
        if result.blocked:
            return result
        
        # Scan end
        if file_size > sample_bytes * 2:
            f.seek(-sample_bytes, 2)  # Seek from end
            tail = f.read(sample_bytes)
            result = content_scanner.scan(tail)
            if result.blocked:
                return result
    
    return ScanResult(blocked=False, sampled=True)
```

### 6.3 Resource Management

```python
class ResourceLimiter:
    """Prevent resource exhaustion during scanning"""
    
    def __init__(self, config):
        self.max_memory_mb = config.max_scan_memory_mb
        self.max_cpu_percent = config.max_scan_cpu_percent
        self.max_concurrent_scans = config.max_concurrent_scans
        
        self.active_scans = 0
        self.semaphore = threading.Semaphore(self.max_concurrent_scans)
    
    @contextmanager
    def acquire_scan_slot(self):
        """Limit concurrent scans"""
        self.semaphore.acquire()
        self.active_scans += 1
        try:
            yield
        finally:
            self.active_scans -= 1
            self.semaphore.release()
    
    def check_resources(self) -> bool:
        """Verify system resources available"""
        import psutil
        
        # Check memory
        mem = psutil.virtual_memory()
        if mem.percent > self.max_memory_mb:
            logger.warning("System memory exhausted, deferring scan")
            return False
        
        # Check CPU
        cpu = psutil.cpu_percent(interval=0.1)
        if cpu > self.max_cpu_percent:
            logger.warning("System CPU saturated, deferring scan")
            return False
        
        return True
```

---

## 7. Security and Privacy

### 7.1 Privacy Considerations

Content scanning raises privacy concerns that must be addressed:

#### 7.1.1 Data Minimization
```python
class ScanResult:
    """Scan results with privacy-aware logging"""
    
    def __init__(self, blocked: bool, reason: str = ""):
        self.blocked = blocked
        self.reason = reason
        self.matched_pattern_type = None  # e.g., "ssn", "credit_card"
        self.matched_value = None  # NEVER LOG THIS
        self.file_hash = None
        self.timestamp = datetime.now()
    
    def to_log_entry(self) -> dict:
        """Generate privacy-safe log entry"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'blocked': self.blocked,
            'pattern_type': self.matched_pattern_type,  # OK to log
            'reason': self.reason,
            'file_hash': self.file_hash,
            # NEVER include matched_value (actual SSN, etc.)
        }
```

**Policy:** Never log actual sensitive values, only pattern types and hashes.

#### 7.1.2 Access Control
```python
class ScannerAccessControl:
    """Ensure only privileged daemon can access scanner"""
    
    def __init__(self):
        self.socket_path = "/run/usb-enforcer/scanner.sock"
        self.required_uid = 0  # root only
    
    def verify_caller(self, connection):
        """Verify caller is authorized daemon"""
        creds = connection.getpeercred()
        
        if creds.uid != self.required_uid:
            logger.warning(f"Unauthorized scanner access from UID {creds.uid}")
            raise PermissionError("Scanner access denied")
        
        return True
```

### 7.2 Security Boundaries

#### 7.2.1 Privilege Separation
```
┌───────────────────────────────────────────────┐
│          usb-enforcerd (root)                 │
│  - Mounts FUSE overlay                        │
│  - Intercepts writes                          │
│  - Makes enforcement decisions                │
└───────────────┬───────────────────────────────┘
                │ Unix socket (locked)
                ▼
┌───────────────────────────────────────────────┐
│     usb-scanner-worker (limited privs)        │
│  - Performs content analysis                  │
│  - Returns scan result only                   │
│  - Cannot access filesystem directly          │
└───────────────────────────────────────────────┘
```

Benefits:
- Scanner worker runs with minimal privileges
- Compromise of scanner doesn't grant root access
- Sandboxing possible (seccomp, AppArmor)

#### 7.2.2 Input Validation
```python
def validate_scan_request(request: ScanRequest) -> bool:
    """Prevent path traversal and injection attacks"""
    
    # Verify path is within USB mount
    real_path = request.filepath.resolve()
    if not str(real_path).startswith('/media/usb-enforcer/'):
        raise SecurityError("Path outside USB mount")
    
    # Verify no symlink escapes
    if real_path.is_symlink():
        target = real_path.readlink()
        if not str(target).startswith('/media/usb-enforcer/'):
            raise SecurityError("Symlink escape attempt")
    
    # Size limits
    if real_path.stat().st_size > MAX_SCAN_SIZE:
        raise ValueError("File too large for scanning")
    
    return True
```

### 7.3 Cryptographic Considerations

#### 7.3.1 Pattern Storage
```python
class SecurePatternStore:
    """Encrypted storage for custom patterns"""
    
    def __init__(self, keyfile: Path):
        self.fernet = Fernet(keyfile.read_bytes())
    
    def add_pattern(self, name: str, regex: str, description: str):
        """Store pattern encrypted at rest"""
        pattern_data = {
            'name': name,
            'regex': regex,
            'description': description,
            'added_by': os.getuid(),
            'timestamp': time.time()
        }
        
        encrypted = self.fernet.encrypt(
            json.dumps(pattern_data).encode()
        )
        
        # Store in protected directory
        pattern_file = PATTERN_DIR / f"{name}.encrypted"
        pattern_file.write_bytes(encrypted)
        pattern_file.chmod(0o600)  # Owner only
```

**Rationale:** Prevents pattern disclosure if system compromised.

---

## 8. Configuration and Policies

### 8.1 Configuration Schema

```toml
# /etc/usb-enforcer/config.toml

[content_scanning]
# Enable/disable content verification
enabled = true

# Scan encrypted USB devices (in addition to block-level enforcement)
scan_encrypted_devices = true

# Performance settings
max_file_size_mb = 500  # Files larger than this: sample or skip
max_scan_time_seconds = 30
max_memory_per_scan_mb = 100
max_concurrent_scans = 4

# Caching
enable_scan_cache = true
cache_size_mb = 100
cache_ttl_hours = 24

[content_scanning.patterns]
# Built-in pattern categories to enable
enabled_categories = [
    "pii",          # SSN, driver's license, passport
    "financial",    # Credit cards, bank accounts
    "corporate",    # API keys, credentials, tokens
]

# Optional: disable specific patterns
disabled_patterns = []

# Custom patterns (regex)
[[content_scanning.patterns.custom]]
name = "employee_id"
regex = "EMP-\\d{6}"
description = "Company employee ID format"
severity = "high"

[[content_scanning.patterns.custom]]
name = "project_codename"
regex = "PROJECT-REDACTED-\\w+"
description = "Confidential project codenames"
severity = "critical"

[content_scanning.archives]
# Enable archive scanning
scan_archives = true

# Maximum nesting depth (zip in zip in zip...)
max_depth = 5

# Maximum files per archive
max_members = 1000

# Handle encrypted/password-protected archives
block_encrypted_archives = true  # or false to skip

# Supported formats
supported_formats = ["zip", "tar", "tar.gz", "tar.bz2", "tar.xz", "7z"]

[content_scanning.documents]
# Enable document format parsing
scan_documents = true

# Supported formats
supported_formats = ["pdf", "docx", "xlsx", "pptx", "odt", "ods"]

[content_scanning.ngrams]
# Enable n-gram analysis
enabled = true

# Thresholds (0.0-1.0)
block_threshold = 0.65  # Block if score >= this
warn_threshold = 0.45   # Log warning if score >= this

# N-gram sizes
character_ngram_size = 3  # Trigrams for digit sequences
word_ngram_size = 2       # Bigrams for sensitive phrases

[content_scanning.entropy]
# Enable entropy analysis
enabled = true

# High entropy threshold (0-8 bits)
threshold = 7.5

# Block size for analysis
block_size_kb = 1

[content_scanning.policy]
# Action on detection
action = "block"  # or "log" or "prompt"

# User notification
notify_user = true
notification_message = "File blocked: contains sensitive data"

# Allow user override (with audit)
allow_override = false  # Requires admin password

# Exemptions
exempt_users = ["backup", "dbadmin"]
exempt_groups = ["usb-exempt"]

# File type exemptions (skip scanning)
exempt_extensions = [".iso", ".img", ".vmdk"]

[content_scanning.logging]
# Audit all scan results
log_all_scans = false  # true = log even clean files

# Log blocked files only
log_blocked_only = true

# Log location
log_to_journald = true
log_to_file = "/var/log/usb-enforcer/content-scans.log"

# Retention
max_log_age_days = 90

# SIEM integration
syslog_enabled = false
syslog_server = "siem.company.com:514"
```

### 8.2 Policy Enforcement Modes

```python
class EnforcementMode(Enum):
    DISABLED = "disabled"    # No content scanning
    MONITOR = "monitor"      # Scan and log, but allow
    WARN = "warn"            # Prompt user, allow override
    BLOCK = "block"          # Block transfer, no override
    QUARANTINE = "quarantine"  # Move to quarantine dir
```

### 8.3 Role-Based Policies

```toml
# Different policies for different user groups

[[content_scanning.role_policies]]
name = "executives"
groups = ["c-suite", "vp"]
mode = "warn"  # Prompt but allow
patterns = ["pii", "financial"]  # Subset of patterns

[[content_scanning.role_policies]]
name = "engineering"
groups = ["developers", "devops"]
mode = "block"
patterns = ["corporate"]  # Block API keys, credentials
exempt_patterns = ["employee_id"]  # But allow internal IDs

[[content_scanning.role_policies]]
name = "contractors"
groups = ["contractor"]
mode = "block"
patterns = ["pii", "financial", "corporate"]  # All patterns
allow_override = false  # No exceptions

[[content_scanning.role_policies]]
name = "default"
mode = "block"
patterns = ["pii", "financial"]
```

---

## 9. Implementation Roadmap

### 9.1 Phase 1: Foundation (4-6 weeks)

**Milestone 1.1: Core Scanning Engine** (2 weeks)
- [ ] Implement pattern matching engine with regex
- [ ] Basic file type detection
- [ ] Configuration loading
- [ ] Unit tests for pattern matching
- [ ] Performance benchmarks

**Milestone 1.2: FUSE Integration** (2 weeks)
- [ ] FUSE filesystem overlay implementation
- [ ] Write interception for encrypted mounts
- [ ] Pass-through for non-USB operations
- [ ] Integration with existing daemon
- [ ] Test with loop devices

**Milestone 1.3: Logging & Audit** (1 week)
- [ ] Structured logging for scan events
- [ ] Journald integration
- [ ] User notifications via existing UI
- [ ] Audit trail implementation

### 9.2 Phase 2: Advanced Features (4-6 weeks)

**Milestone 2.1: Archive Support** (2 weeks)
- [ ] ZIP scanner implementation
- [ ] TAR scanner implementation
- [ ] 7Z and RAR support
- [ ] Recursive extraction with depth limits
- [ ] Encrypted archive handling

**Milestone 2.2: Document Formats** (2 weeks)
- [ ] PDF text extraction
- [ ] DOCX/XLSX parsing
- [ ] ODF format support
- [ ] Table and metadata scanning

**Milestone 2.3: N-gram Analysis** (1 week)
- [ ] Character n-gram implementation
- [ ] Word n-gram implementation
- [ ] Scoring system
- [ ] Threshold tuning

**Milestone 2.4: Performance Optimization** (1 week)
- [ ] Caching layer
- [ ] Streaming for large files
- [ ] Parallel scanning
- [ ] Resource limits

### 9.3 Phase 3: Production Readiness (4 weeks)

**Milestone 3.1: Security Hardening** (1 week)
- [ ] Privilege separation
- [ ] Input validation
- [ ] Pattern encryption
- [ ] Security audit

**Milestone 3.2: Testing** (2 weeks)
- [ ] Unit test suite (100+ tests)
- [ ] Integration tests with real devices
- [ ] Performance regression tests
- [ ] Security penetration testing
- [ ] False positive analysis

**Milestone 3.3: Documentation** (1 week)
- [ ] User configuration guide
- [ ] Administrator deployment guide
- [ ] Pattern development guide
- [ ] Troubleshooting documentation
- [ ] API documentation

### 9.4 Phase 4: Optional Enhancements (Future)

**Milestone 4.1: Machine Learning**
- [ ] Document classification models
- [ ] Anomaly detection
- [ ] Custom model training

**Milestone 4.2: Advanced Features**
- [ ] OCR for images
- [ ] Steganography detection
- [ ] Network-based pattern updates
- [ ] Central management console

---

## 10. Testing Strategy

### 10.1 Unit Tests

```python
# tests/unit/test_pattern_matching.py

class TestPatternMatching:
    def test_ssn_detection_standard_format(self):
        scanner = PatternScanner()
        result = scanner.scan("My SSN is 123-45-6789")
        assert result.blocked is True
        assert result.pattern_type == "ssn"
    
    def test_ssn_detection_no_dashes(self):
        result = scanner.scan("SSN: 123456789")
        assert result.blocked is True
    
    def test_ssn_false_positive_prevention(self):
        # Should not match dates
        result = scanner.scan("Date: 2024-01-15")
        assert result.blocked is False
    
    def test_credit_card_with_luhn_validation(self):
        result = scanner.scan("Card: 4532-1488-0343-6467")
        assert result.blocked is True
        
        # Invalid Luhn checksum
        result = scanner.scan("Card: 4532-1488-0343-6468")
        assert result.blocked is False
```

### 10.2 Integration Tests

```python
# tests/integration/test_content_scanning.py

@pytest.mark.integration
class TestContentScanning:
    def test_block_file_with_ssn(self, fuse_mount, temp_file):
        """Test that file with SSN is blocked"""
        
        # Create file with sensitive data
        sensitive_file = temp_file("test.txt")
        sensitive_file.write_text("SSN: 123-45-6789")
        
        # Attempt to copy to USB
        dest = fuse_mount / "test.txt"
        result = subprocess.run(
            ["cp", str(sensitive_file), str(dest)],
            capture_output=True
        )
        
        # Should fail with permission denied
        assert result.returncode != 0
        assert not dest.exists()
        
        # Check audit log
        logs = get_journald_logs(pattern="content_blocked")
        assert len(logs) > 0
        assert logs[0]['pattern_type'] == 'ssn'
    
    def test_allow_clean_file(self, fuse_mount, temp_file):
        """Test that clean file is allowed"""
        
        clean_file = temp_file("clean.txt")
        clean_file.write_text("This is innocuous content")
        
        dest = fuse_mount / "clean.txt"
        result = subprocess.run(
            ["cp", str(clean_file), str(dest)],
            capture_output=True
        )
        
        assert result.returncode == 0
        assert dest.exists()
        assert dest.read_text() == clean_file.read_text()
```

### 10.3 Performance Tests

```python
# tests/performance/test_scan_speed.py

class TestScanPerformance:
    def test_small_file_scan_time(self):
        """1KB file should scan in <10ms"""
        content = "Clean content " * 100  # ~1KB
        
        start = time.perf_counter()
        result = scanner.scan(content)
        duration = time.perf_counter() - start
        
        assert duration < 0.010  # 10ms
    
    def test_medium_file_scan_time(self):
        """1MB file should scan in <200ms"""
        content = "Clean content " * 100000  # ~1MB
        
        start = time.perf_counter()
        result = scanner.scan(content)
        duration = time.perf_counter() - start
        
        assert duration < 0.200  # 200ms
    
    @pytest.mark.slow
    def test_large_archive_scan(self):
        """Large archive should complete within timeout"""
        archive = create_test_archive(
            num_files=100,
            avg_size_kb=100
        )  # 10MB archive
        
        start = time.perf_counter()
        result = scanner.scan_archive(archive)
        duration = time.perf_counter() - start
        
        assert duration < 5.0  # 5 seconds
```

### 10.4 False Positive Testing

```python
# tests/validation/test_false_positives.py

class TestFalsePositives:
    """Ensure common content doesn't trigger false positives"""
    
    def test_dates_not_detected_as_ssn(self):
        content = "Meeting on 2024-01-15 at 3pm"
        assert scanner.scan(content).blocked is False
    
    def test_phone_numbers_not_credit_cards(self):
        content = "Call me at 555-1234-5678"
        assert scanner.scan(content).blocked is False
    
    def test_git_commits_not_api_keys(self):
        content = "commit abc123def456789"
        assert scanner.scan(content).blocked is False
    
    def test_random_base64_not_jwt(self):
        # JWT has specific format: header.payload.signature
        content = "Random base64: " + base64.b64encode(os.urandom(32))
        assert scanner.scan(content).blocked is False
```

---

## 11. Operational Considerations

### 11.1 Deployment Architecture

```
┌────────────────────────────────────────────────────────┐
│                  Enterprise Deployment                  │
└────────────────────────────────────────────────────────┘

  Desktop Endpoints (1000s)
  ├─ usb-enforcerd + scanner
  ├─ Local pattern cache
  └─ Local audit logs
         │
         │ (rsyslog/filebeat)
         ▼
  ┌──────────────────────┐
  │  Central Log Server  │
  │  - Aggregates audit  │
  │  - Pattern violations│
  │  - Dashboard/alerts  │
  └──────────────────────┘
         │
         ▼
  ┌──────────────────────┐
  │  SIEM Integration    │
  │  - Splunk, ELK, etc. │
  │  - Compliance reports│
  └──────────────────────┘

  Optional: Central Management
  ┌──────────────────────┐
  │  Config Server       │
  │  - Pattern updates   │
  │  - Policy distribution│
  │  - Fleet management  │
  └──────────────────────┘
```

### 11.2 Monitoring and Alerting

```yaml
# Prometheus metrics

# Scan statistics
usb_enforcer_scans_total{result="blocked|allowed"}
usb_enforcer_scan_duration_seconds{quantile="0.5|0.9|0.99"}
usb_enforcer_false_positives_total

# Pattern matches
usb_enforcer_pattern_matches{type="ssn|credit_card|api_key"}

# Performance
usb_enforcer_cache_hits_total
usb_enforcer_cache_misses_total
usb_enforcer_memory_usage_bytes
usb_enforcer_active_scans

# Errors
usb_enforcer_scan_errors_total{reason="timeout|oom|corrupt"}
```

### 11.3 Troubleshooting Guide

#### Common Issues

**Issue: High false positive rate**
```bash
# Check pattern configuration
sudo usb-enforcer-cli patterns list --verbose

# Test specific pattern
echo "test content" | sudo usb-enforcer-cli scan --pattern ssn

# Tune threshold
sudo vi /etc/usb-enforcer/config.toml
# [content_scanning.ngrams]
# block_threshold = 0.75  # Increase from 0.65
```

**Issue: Slow scan performance**
```bash
# Check scan times
journalctl -u usb-enforcerd | grep scan_duration

# Enable caching if disabled
sudo usb-enforcer-cli config set content_scanning.enable_scan_cache true

# Reduce scan scope
sudo usb-enforcer-cli config set content_scanning.max_file_size_mb 100
```

**Issue: Files incorrectly blocked**
```bash
# Review recent blocks
sudo usb-enforcer-cli logs --blocked --last 24h

# Test file manually
sudo usb-enforcer-cli scan /path/to/file --verbose

# Whitelist file by hash
sudo usb-enforcer-cli whitelist add --hash <sha256> --reason "Known safe"
```

### 11.4 Compliance Reporting

```python
# scripts/generate-compliance-report.py

def generate_monthly_report(year, month):
    """Generate DLP compliance report"""
    
    events = query_audit_logs(year, month)
    
    report = {
        'period': f"{year}-{month:02d}",
        'total_transfers': events['total'],
        'blocked_transfers': events['blocked'],
        'block_rate': events['blocked'] / events['total'],
        
        'by_pattern_type': {
            'pii': events['pii_blocks'],
            'financial': events['financial_blocks'],
            'corporate': events['corporate_blocks'],
        },
        
        'by_user': events['by_user'],
        'by_department': events['by_department'],
        
        'top_violations': events['top_10_users'],
        
        'policy_overrides': events['overrides'],
        'false_positives': events['false_positives'],
        
        'incidents_requiring_review': [
            e for e in events 
            if e['severity'] == 'critical'
        ]
    }
    
    return report
```

---

## Conclusion

The proposed content verification system enhances USB Enforcer with comprehensive data loss prevention capabilities while maintaining the tool's core principles of transparency, performance, and security. By combining pattern matching, n-gram analysis, archive scanning, and format-specific handlers, the system provides robust protection against both intentional and accidental sensitive data exfiltration.

### Key Benefits

1. **Layered Defense**: Block device encryption + content verification
2. **Regulatory Compliance**: Automated PII/PHI/PCI detection
3. **Minimal Impact**: <100ms overhead for typical operations
4. **Flexible Configuration**: Organization-specific policies and patterns
5. **Comprehensive Audit**: Full visibility into data transfers

### Next Steps

1. **Prototype Development** (Phase 1)
2. **Internal Testing** (Phase 2-3)
3. **Security Audit** (Phase 3)
4. **Beta Deployment** (Select organizations)
5. **General Availability** (Full release)

### References

- NIST SP 800-53: Security and Privacy Controls
- OWASP DLP Best Practices
- Linux FUSE Documentation: https://www.kernel.org/doc/html/latest/filesystems/fuse.html
- GDPR Article 32: Security of Processing
- HIPAA Security Rule: 45 CFR Part 164

---

**Document History**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-11 | USB Enforcer Team | Initial whitepaper |

**Contact**

For questions or feedback on this proposal, contact the USB Enforcer development team.

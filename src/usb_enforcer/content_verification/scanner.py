"""
Core content scanning functionality.

Provides the main ContentScanner class that orchestrates pattern matching,
file format detection, and scanning decisions.
"""

import os
import time
import hashlib
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, BinaryIO
from dataclasses import dataclass, field
from enum import Enum
from collections import OrderedDict

from .patterns import PatternLibrary, PatternMatch
from .ngram_analyzer import NgramAnalyzer


logger = logging.getLogger(__name__)


class ScanAction(Enum):
    """Actions to take based on scan results"""
    ALLOW = "allow"
    BLOCK = "block"
    WARN = "warn"
    QUARANTINE = "quarantine"


@dataclass
class ScanResult:
    """
    Result of a content scan operation.
    
    This class contains all information about a scan, including whether
    the content should be blocked and why.
    """
    blocked: bool
    action: ScanAction
    reason: str = ""
    matches: List[PatternMatch] = field(default_factory=list)
    file_path: Optional[str] = None
    file_hash: Optional[str] = None
    scan_duration: float = 0.0
    timestamp: float = field(default_factory=time.time)
    suspicious_score: float = 0.0
    
    # Additional metadata
    file_size: int = 0
    file_type: str = ""
    sampled: bool = False
    location: str = ""  # For archives: "archive.zip:file.txt"
    
    def to_log_dict(self) -> Dict[str, Any]:
        """
        Generate privacy-safe log entry.
        
        IMPORTANT: Never includes actual matched values, only pattern types.
        """
        return {
            'timestamp': self.timestamp,
            'blocked': self.blocked,
            'action': self.action.value,
            'reason': self.reason,
            'file_hash': self.file_hash,
            'file_size': self.file_size,
            'file_type': self.file_type,
            'scan_duration': self.scan_duration,
            'suspicious_score': self.suspicious_score,
            'sampled': self.sampled,
            'location': self.location,
            'pattern_matches': [
                {
                    'pattern_name': m.pattern_name,
                    'pattern_category': m.pattern_category,
                    'severity': m.severity,
                    'position': m.position,
                    # Never log matched_text!
                }
                for m in self.matches
            ]
        }
    
    def get_summary(self) -> str:
        """Get human-readable summary"""
        if not self.blocked:
            return "Content allowed: no sensitive data detected"
        
        if self.matches:
            patterns = ', '.join(set(m.pattern_name for m in self.matches))
            return f"Content blocked: detected {patterns}"
        
        return f"Content blocked: {self.reason}"


class ScanCache:
    """
    LRU cache for scan results.
    
    Caches scan results by file hash to avoid redundant scanning of
    unchanged files.
    """
    
    def __init__(self, max_size_mb: int = 100, ttl_hours: Optional[int] = None):
        """
        Initialize cache.
        
        Args:
            max_size_mb: Maximum cache size in megabytes
        """
        self.cache: Dict[str, ScanResult] = {}
        self.lru: OrderedDict = OrderedDict()
        self.entry_sizes: Dict[str, int] = {}
        self.entry_times: Dict[str, float] = {}
        self.max_size = max_size_mb * 1024 * 1024
        self.current_size = 0
        self.hits = 0
        self.misses = 0
        self.ttl_seconds = None if ttl_hours is None else ttl_hours * 3600
    
    def get(self, file_hash: str) -> Optional[ScanResult]:
        """
        Get cached scan result.
        
        Args:
            file_hash: SHA256 hash of file
            
        Returns:
            Cached ScanResult if found, None otherwise
        """
        if file_hash in self.cache:
            if self.ttl_seconds is not None:
                entry_time = self.entry_times.get(file_hash, 0)
                if time.time() - entry_time > self.ttl_seconds:
                    self._evict(file_hash)
                    self.misses += 1
                    return None
            # Update LRU order
            self.lru.move_to_end(file_hash)
            self.hits += 1
            logger.debug(f"Cache hit for {file_hash[:16]}...")
            return self.cache[file_hash]
        
        self.misses += 1
        return None
    
    def put(self, file_hash: str, result: ScanResult, file_size: int) -> None:
        """
        Store scan result in cache.
        
        Args:
            file_hash: SHA256 hash of file
            result: Scan result to cache
            file_size: Size of file in bytes
        """
        # Evict entries if needed
        while self.current_size + file_size > self.max_size and self.lru:
            oldest_hash = next(iter(self.lru))
            self._evict(oldest_hash)

        self.cache[file_hash] = result
        self.lru[file_hash] = True
        self.entry_sizes[file_hash] = file_size
        self.entry_times[file_hash] = time.time()
        self.current_size += file_size
        logger.debug(f"Cached result for {file_hash[:16]}... (cache size: {self.current_size / 1024 / 1024:.1f} MB)")
    
    def clear(self) -> None:
        """Clear all cached entries"""
        self.cache.clear()
        self.lru.clear()
        self.entry_sizes.clear()
        self.entry_times.clear()
        self.current_size = 0
        self.hits = 0
        self.misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'entries': len(self.cache),
            'size_mb': self.current_size / 1024 / 1024,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': hit_rate,
        }

    def _evict(self, file_hash: str) -> None:
        size = self.entry_sizes.pop(file_hash, 0)
        self.entry_times.pop(file_hash, None)
        self.cache.pop(file_hash, None)
        self.lru.pop(file_hash, None)
        self.current_size -= size


class ContentScanner:
    """
    Main content scanning engine.
    
    Orchestrates pattern matching, file format detection, and scanning
    decisions for USB content verification.
    """
    
    # File size thresholds
    SMALL_FILE_THRESHOLD = 1 * 1024 * 1024  # 1 MB - always full scan
    LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100 MB - sample only
    
    # Chunk size for streaming large files
    CHUNK_SIZE = 1024 * 1024  # 1 MB
    
    # High-risk extensions that always get full scan
    HIGH_RISK_EXTENSIONS = {
        '.txt', '.csv', '.json', '.xml', '.log', '.conf', '.cfg',
        '.ini', '.yaml', '.yml', '.toml', '.env', '.key', '.pem',
        '.sql', '.sh', '.bat', '.ps1', '.py', '.js', '.java',
        '.eml',  # Email (text-based RFC 822 format)
    }
    
    # Extensions to skip (binary formats that can't contain text secrets)
    SKIP_EXTENSIONS = {
        '.iso', '.img', '.vmdk', '.vdi', '.qcow2',
        '.mp4', '.avi', '.mkv', '.mp3', '.wav', '.flac',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico',
        '.exe', '.dll', '.so', '.dylib',
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize content scanner.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        
        # Initialize pattern library
        enabled_categories = self.config.get('enabled_categories', ['pii', 'financial', 'corporate'])
        disabled_patterns = self.config.get('disabled_patterns', [])
        self.pattern_library = PatternLibrary(enabled_categories, disabled_patterns)
        
        # Load custom patterns
        for custom_pattern in self.config.get('custom_patterns', []):
            self.pattern_library.add_custom_pattern(
                name=custom_pattern['name'],
                regex=custom_pattern['regex'],
                description=custom_pattern.get('description', ''),
                severity=custom_pattern.get('severity', 'high')
            )
        
        # Initialize cache
        cache_enabled = self.config.get('enable_cache', True)
        cache_size_mb = self.config.get('cache_size_mb', 100)
        cache_ttl_hours = self.config.get('cache_ttl_hours')
        self.cache = ScanCache(cache_size_mb, cache_ttl_hours) if cache_enabled else None
        
        # Configuration
        max_file_size_mb = self.config.get('max_file_size_mb', 500)
        self.max_file_size = None if max_file_size_mb <= 0 else max_file_size_mb * 1024 * 1024
        self.max_scan_time = self.config.get('max_scan_time_seconds', 30)
        self.block_threshold = self.config.get('block_threshold', 0.65)
        self.action_mode = self.config.get('action', 'block')
        if self.action_mode == "log_only":
            self.action_mode = "allow"
        self.large_file_scan_mode = self.config.get('large_file_scan_mode', 'sampled')
        self.warn_threshold = self.config.get('warn_threshold', 0.45)
        self.ngram_enabled = self.config.get('ngram_enabled', True)
        self.ngram_analyzer = NgramAnalyzer(
            char_ngram_size=self.config.get('ngram_character_size', 3),
            word_ngram_size=self.config.get('ngram_word_size', 2),
        )
        
        logger.info(f"Content scanner initialized with {len(self.pattern_library.get_all_patterns())} patterns")
    
    def scan_file(self, filepath: Path) -> ScanResult:
        """
        Scan a file for sensitive content.
        
        Args:
            filepath: Path to file to scan
            
        Returns:
            ScanResult indicating whether to block the file
        """
        start_time = time.time()
        
        try:
            # Basic validation
            if not filepath.exists():
                return ScanResult(
                    blocked=False,
                    action=ScanAction.ALLOW,
                    reason="File does not exist"
                )
            
            if not filepath.is_file():
                return ScanResult(
                    blocked=False,
                    action=ScanAction.ALLOW,
                    reason="Not a file"
                )
            
            file_size = filepath.stat().st_size
            file_extension = filepath.suffix.lower()
            
            # Detect actual file type via magic numbers (prevent extension spoofing)
            real_file_type = self._detect_real_file_type(filepath)
            extension_mismatch = self._check_extension_mismatch(file_extension, real_file_type)
            
            # If extension is suspicious (mismatch detected), force full scan
            if extension_mismatch:
                logger.warning(f"Extension mismatch detected: {filepath.name} claims {file_extension} but is {real_file_type}")
                # Don't skip - force scan even if extension is in SKIP_EXTENSIONS
            else:
                # Check if extension should be skipped (only if no mismatch)
                if file_extension in self.SKIP_EXTENSIONS:
                    logger.debug(f"Skipping {filepath.name} (exempt extension)")
                    return ScanResult(
                        blocked=False,
                        action=ScanAction.ALLOW,
                        reason="Exempt file type",
                        file_size=file_size,
                        file_type=file_extension
                    )
            
            # Check file size
            if self.max_file_size is not None and file_size > self.max_file_size:
                logger.warning(f"File too large: {filepath.name} ({file_size} bytes)")
                return ScanResult(
                    blocked=True,
                    action=ScanAction.BLOCK,
                    reason=f"File exceeds size limit ({self.max_file_size / 1024 / 1024:.1f} MB)",
                    file_size=file_size,
                    file_type=file_extension
                )
            
            # Compute file hash
            file_hash = self._compute_file_hash(filepath)
            
            # Check cache
            if self.cache:
                cached_result = self.cache.get(file_hash)
                if cached_result:
                    cached_result.scan_duration = time.time() - start_time
                    return cached_result
            
            # Determine scan strategy based on file size
            if file_size < self.SMALL_FILE_THRESHOLD:
                result = self._scan_small_file(filepath, file_hash)
            elif file_size < self.LARGE_FILE_THRESHOLD:
                result = self._scan_medium_file(filepath, file_hash)
            else:
                result = self._scan_large_file(filepath, file_hash)
            if time.time() - start_time > self.max_scan_time:
                return self._timeout_result(start_time)
            
            # Set metadata
            result.file_path = str(filepath)
            result.file_size = file_size
            result.file_type = file_extension
            result.scan_duration = time.time() - start_time
            
            # Cache result
            if self.cache and not result.blocked:
                self.cache.put(file_hash, result, file_size)
            
            logger.debug(f"Scanned {filepath.name} in {result.scan_duration:.3f}s: {result.get_summary()}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error scanning {filepath}: {e}", exc_info=True)
            
            # Fail-safe behavior based on configuration
            if self.config.get('block_on_error', True):
                return ScanResult(
                    blocked=True,
                    action=ScanAction.BLOCK,
                    reason=f"Scan error: {str(e)}",
                    scan_duration=time.time() - start_time
                )
            else:
                return ScanResult(
                    blocked=False,
                    action=ScanAction.ALLOW,
                    reason=f"Scan error (allowed): {str(e)}",
                    scan_duration=time.time() - start_time
                )
    
    def scan_content(self, content: bytes, filename: str = "unknown") -> ScanResult:
        """
        Scan raw content for sensitive data.
        
        Args:
            content: Raw bytes to scan
            filename: Optional filename for context
            
        Returns:
            ScanResult indicating whether to block the content
        """
        start_time = time.time()
        
        try:
            # Try to decode as text
            try:
                text = content.decode('utf-8', errors='ignore')
            except:
                text = content.decode('latin-1', errors='ignore')
            
            # Scan for patterns
            matches = self.pattern_library.scan_text(text)
            suspicious_score = 0.0
            if self.ngram_enabled:
                suspicious_score = self.ngram_analyzer.score_content(text)
            
            # Determine action
            if matches:
                # Found sensitive data
                action = ScanAction[self.action_mode.upper()]
                blocked = action == ScanAction.BLOCK
                
                # Get highest severity match
                critical_matches = [m for m in matches if m.severity == 'critical']
                reason = f"Detected {len(matches)} sensitive pattern(s)"
                if critical_matches:
                    reason += f" including {len(critical_matches)} critical"
                
                return ScanResult(
                    blocked=blocked,
                    action=action,
                    reason=reason,
                    matches=matches,
                    file_size=len(content),
                    scan_duration=time.time() - start_time,
                    suspicious_score=suspicious_score
                )
            if self.ngram_enabled and suspicious_score >= self.warn_threshold:
                action = ScanAction.WARN
                blocked = False
                if suspicious_score >= self.block_threshold:
                    action = ScanAction.BLOCK
                    blocked = True
                return ScanResult(
                    blocked=blocked,
                    action=action,
                    reason="Suspicious content detected by n-gram analysis",
                    file_size=len(content),
                    scan_duration=time.time() - start_time,
                    suspicious_score=suspicious_score
                )
            else:
                return ScanResult(
                    blocked=False,
                    action=ScanAction.ALLOW,
                    reason="No sensitive data detected",
                    file_size=len(content),
                    scan_duration=time.time() - start_time,
                    suspicious_score=suspicious_score
                )
                
        except Exception as e:
            logger.error(f"Error scanning content: {e}", exc_info=True)
            
            return self._error_result(str(e), start_time)

    def _timeout_result(self, start_time: float) -> ScanResult:
        reason = f"Scan timeout exceeded ({self.max_scan_time}s)"
        if self.config.get('block_on_error', True):
            return ScanResult(
                blocked=True,
                action=ScanAction.BLOCK,
                reason=reason,
                scan_duration=time.time() - start_time
            )
        return ScanResult(
            blocked=False,
            action=ScanAction.ALLOW,
            reason=reason,
            scan_duration=time.time() - start_time
        )

    def _error_result(self, error: str, start_time: float) -> ScanResult:
        if self.config.get('block_on_error', True):
            return ScanResult(
                blocked=True,
                action=ScanAction.BLOCK,
                reason=f"Scan error: {error}",
                scan_duration=time.time() - start_time
            )
        return ScanResult(
            blocked=False,
            action=ScanAction.ALLOW,
            reason=f"Scan error (allowed): {error}",
            scan_duration=time.time() - start_time
        )
    
    def _scan_small_file(self, filepath: Path, file_hash: str) -> ScanResult:
        """Scan small file completely in memory"""
        logger.debug(f"Full scan: {filepath.name}")
        
        content = filepath.read_bytes()
        result = self.scan_content(content, filepath.name)
        result.file_hash = file_hash
        
        return result
    
    def _scan_medium_file(self, filepath: Path, file_hash: str) -> ScanResult:
        """Scan medium file with chunking"""
        logger.debug(f"Chunked scan: {filepath.name}")
        
        all_matches = []
        
        with open(filepath, 'rb') as f:
            # Read and scan in chunks with overlap
            previous_chunk = b''
            
            while True:
                chunk = f.read(self.CHUNK_SIZE)
                if not chunk:
                    break
                
                # Combine with end of previous chunk to catch patterns spanning boundaries
                scan_content = previous_chunk[-1000:] + chunk  # 1KB overlap
                
                try:
                    text = scan_content.decode('utf-8', errors='ignore')
                except:
                    text = scan_content.decode('latin-1', errors='ignore')
                
                matches = self.pattern_library.scan_text(text)
                all_matches.extend(matches)
                
                # Early exit if critical pattern found
                if any(m.severity == 'critical' for m in matches):
                    break
                
                previous_chunk = chunk
        
        # Generate result
        if all_matches:
            action = ScanAction[self.action_mode.upper()]
            blocked = action == ScanAction.BLOCK
            
            return ScanResult(
                blocked=blocked,
                action=action,
                reason=f"Detected {len(all_matches)} sensitive pattern(s)",
                matches=all_matches,
                file_hash=file_hash
            )
        else:
            return ScanResult(
                blocked=False,
                action=ScanAction.ALLOW,
                reason="No sensitive data detected",
                file_hash=file_hash
            )
    
    def _scan_large_file(self, filepath: Path, file_hash: str) -> ScanResult:
        """
        Scan large file using sampling strategy.
        
        Scans first and last few MB to balance performance and detection.
        """
        if self.large_file_scan_mode == "full":
            return self._scan_medium_file(filepath, file_hash)
        logger.debug(f"Sampling scan: {filepath.name}")
        
        sample_size = 5 * 1024 * 1024  # 5 MB
        file_size = filepath.stat().st_size
        
        all_matches = []
        
        with open(filepath, 'rb') as f:
            # Scan beginning
            head = f.read(sample_size)
            result = self.scan_content(head, filepath.name)
            all_matches.extend(result.matches)
            
            # Scan end if file is large enough
            if file_size > sample_size * 2:
                f.seek(-sample_size, 2)  # Seek from end
                tail = f.read(sample_size)
                result = self.scan_content(tail, filepath.name)
                all_matches.extend(result.matches)
        
        # Generate result
        if all_matches:
            action = ScanAction[self.action_mode.upper()]
            blocked = action == ScanAction.BLOCK
            
            return ScanResult(
                blocked=blocked,
                action=action,
                reason=f"Detected {len(all_matches)} sensitive pattern(s) (sampled)",
                matches=all_matches,
                file_hash=file_hash,
                sampled=True
            )
        else:
            return ScanResult(
                blocked=False,
                action=ScanAction.ALLOW,
                reason="No sensitive data detected (sampled)",
                file_hash=file_hash,
                sampled=True
            )
    
    def _compute_file_hash(self, filepath: Path) -> str:
        """Compute SHA256 hash of file"""
        sha256 = hashlib.sha256()
        
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                sha256.update(chunk)
        
        return sha256.hexdigest()
    
    def _detect_real_file_type(self, filepath: Path) -> Optional[str]:
        """
        Detect actual file type using magic numbers (file signatures).
        
        This prevents extension-based evasion where someone renames
        passwords.txt to passwords.jpg to bypass scanning.
        
        Args:
            filepath: Path to file
            
        Returns:
            Detected MIME type or description (e.g., 'text/plain', 'image/jpeg')
        """
        try:
            import magic
        except ImportError:
            # If python-magic not installed, skip detection
            logger.debug("python-magic not installed, skipping file type detection")
            return None
        
        try:
            # Try to detect via magic
            mime = magic.Magic(mime=True)
            detected_type = mime.from_file(str(filepath))
            return detected_type
        except Exception as e:
            logger.debug(f"Error detecting file type for {filepath.name}: {e}")
            return None
    
    def _check_extension_mismatch(self, claimed_extension: str, real_type: Optional[str]) -> bool:
        """
        Check if file extension matches actual content.
        
        Returns True if there's a suspicious mismatch (e.g., text file
        claiming to be an image).
        
        Args:
            claimed_extension: File extension (e.g., '.jpg')
            real_type: Detected MIME type (e.g., 'text/plain')
            
        Returns:
            True if mismatch is suspicious
        """
        if not real_type:
            # Can't detect, assume no mismatch
            return False
        
        # Define expected MIME types for extensions
        EXTENSION_MIME_MAP = {
            # Images (should skip)
            '.jpg': ['image/jpeg'],
            '.jpeg': ['image/jpeg'],
            '.png': ['image/png'],
            '.gif': ['image/gif'],
            '.bmp': ['image/bmp', 'image/x-ms-bmp'],
            '.ico': ['image/x-icon', 'image/vnd.microsoft.icon'],
            
            # Videos (should skip)
            '.mp4': ['video/mp4'],
            '.avi': ['video/x-msvideo'],
            '.mkv': ['video/x-matroska'],
            
            # Audio (should skip)
            '.mp3': ['audio/mpeg'],
            '.wav': ['audio/wav', 'audio/x-wav'],
            '.flac': ['audio/flac'],
            
            # Executables (should skip)
            '.exe': ['application/x-dosexec', 'application/x-executable'],
            '.dll': ['application/x-dosexec'],
            '.so': ['application/x-sharedlib', 'application/x-executable'],
            
            # Disk images (should skip)
            '.iso': ['application/x-iso9660-image'],
            '.img': ['application/octet-stream'],
            '.vmdk': ['application/octet-stream'],
        }
        
        expected_types = EXTENSION_MIME_MAP.get(claimed_extension, [])
        
        # If extension claims to be a binary/skip type but content is text, that's suspicious
        if claimed_extension in self.SKIP_EXTENSIONS:
            # Check if real content is actually text or document
            if real_type.startswith('text/') or \
               real_type in ('application/json', 'application/xml', 'application/csv'):
                logger.warning(f"Suspicious: File claims {claimed_extension} but contains {real_type}")
                return True
            
            # Check if claims specific binary type but doesn't match
            if expected_types and real_type not in expected_types:
                # Be lenient with generic application/octet-stream
                if real_type != 'application/octet-stream':
                    logger.warning(f"Type mismatch: {claimed_extension} expects {expected_types} but got {real_type}")
                    return True
        
        return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get scanner statistics"""
        stats = {
            'patterns_loaded': len(self.pattern_library.get_all_patterns()),
            'patterns_by_category': {},
        }
        
        # Count patterns by category
        for pattern in self.pattern_library.get_all_patterns():
            category = pattern.category.value
            stats['patterns_by_category'][category] = stats['patterns_by_category'].get(category, 0) + 1
        
        # Add cache stats if enabled
        if self.cache:
            stats['cache'] = self.cache.get_stats()
        
        return stats

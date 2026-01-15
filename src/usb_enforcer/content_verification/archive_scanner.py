"""
Archive scanner for recursive content analysis.

Supports ZIP, TAR (and variants), 7Z, and RAR archives with
configurable depth limits and security protections.
"""

import zipfile
import tarfile
import logging
import time
from pathlib import Path
from typing import Optional, List, BinaryIO
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass
class ArchiveConfig:
    """Configuration for archive scanning"""
    max_depth: int = 5
    max_members: int = 1000
    max_extract_size_mb: int = 100
    scan_timeout_seconds: int = 30
    block_encrypted_archives: bool = True
    supported_formats: List[str] = None
    
    def __post_init__(self):
        if self.supported_formats is None:
            self.supported_formats = ['zip', 'tar', 'tar.gz', 'tar.bz2', 'tar.xz', '7z']


class ArchiveScanner:
    """
    Recursive archive scanner.
    
    Extracts and scans archive contents with protection against
    zip bombs, nesting attacks, and resource exhaustion.
    """
    
    ARCHIVE_EXTENSIONS = {
        '.zip': 'zip',
        '.jar': 'zip',  # Java Archive (ZIP-based)
        '.war': 'zip',  # Web Application Archive (ZIP-based)
        '.ear': 'zip',  # Enterprise Archive (ZIP-based)
        '.tar': 'tar',
        '.tgz': 'tar.gz',
        '.tar.gz': 'tar.gz',
        '.tar.bz2': 'tar.bz2',
        '.tbz2': 'tar.bz2',
        '.tar.xz': 'tar.xz',
        '.txz': 'tar.xz',
        '.gz': 'gzip',  # Standalone gzip
        '.bz2': 'bzip2',  # Standalone bzip2
        '.xz': 'xz',  # Standalone xz
        '.7z': '7z',
        '.rar': 'rar',
    }
    
    def __init__(self, content_scanner, config: Optional[ArchiveConfig] = None):
        """
        Initialize archive scanner.
        
        Args:
            content_scanner: ContentScanner instance for scanning extracted files
            config: Archive scanning configuration
        """
        self.content_scanner = content_scanner
        self.config = config or ArchiveConfig()
        self.max_extract_size = self.config.max_extract_size_mb * 1024 * 1024
        
        logger.info(f"Archive scanner initialized (max depth: {self.config.max_depth}, "
                   f"max members: {self.config.max_members})")
    
    def is_archive(self, filepath: Path) -> bool:
        """
        Check if file is an archive.
        
        Args:
            filepath: Path to check
            
        Returns:
            True if file is a supported archive format
        """
        # Check by extension
        for ext in self.ARCHIVE_EXTENSIONS:
            if str(filepath).lower().endswith(ext):
                archive_type = self.ARCHIVE_EXTENSIONS[ext]
                return archive_type in self.config.supported_formats
        
        return False
    
    def scan_archive(self, filepath: Path, depth: int = 0):
        """
        Recursively scan archive contents.
        
        Args:
            filepath: Path to archive file
            depth: Current nesting depth
            
        Returns:
            ScanResult from content scanner
        """
        from .scanner import ScanResult, ScanAction
        
        logger.debug(f"Scanning archive: {filepath.name} (depth: {depth})")
        
        # Depth limit check
        if depth > self.config.max_depth:
            logger.warning(f"Archive nesting exceeds limit: {filepath.name}")
            return ScanResult(
                blocked=True,
                action=ScanAction.BLOCK,
                reason=f"Archive nesting exceeds limit ({self.config.max_depth})",
                location=str(filepath)
            )
        
        # Timeout protection
        start_time = time.time()
        
        # Determine archive type
        archive_type = self._get_archive_type(filepath)
        if not archive_type:
            logger.debug(f"Unknown archive type: {filepath.name}")
            return ScanResult(
                blocked=False,
                action=ScanAction.ALLOW,
                reason="Unknown archive type"
            )
        
        # Scan based on type
        try:
            if archive_type.startswith('tar'):
                return self._scan_tar_archive(filepath, depth, start_time)
            elif archive_type == 'zip':
                return self._scan_zip_archive(filepath, depth, start_time)
            elif archive_type == '7z':
                return self._scan_7z_archive(filepath, depth, start_time)
            elif archive_type == 'rar':
                return self._scan_rar_archive(filepath, depth, start_time)
            elif archive_type in ('gzip', 'bzip2', 'xz'):
                return self._scan_compressed_file(filepath, archive_type, depth, start_time)
            else:
                return ScanResult(
                    blocked=False,
                    action=ScanAction.ALLOW,
                    reason=f"Unsupported archive type: {archive_type}"
                )
                
        except Exception as e:
            logger.error(f"Error scanning archive {filepath.name}: {e}", exc_info=True)
            
            if self.content_scanner.config.get('block_on_error', True):
                return ScanResult(
                    blocked=True,
                    action=ScanAction.BLOCK,
                    reason=f"Archive scan error: {str(e)}"
                )
            else:
                return ScanResult(
                    blocked=False,
                    action=ScanAction.ALLOW,
                    reason=f"Archive scan error (allowed): {str(e)}"
                )
    
    def _get_archive_type(self, filepath: Path) -> Optional[str]:
        """Determine archive type from file"""
        for ext, archive_type in self.ARCHIVE_EXTENSIONS.items():
            if str(filepath).lower().endswith(ext):
                return archive_type
        return None
    
    def _check_timeout(self, start_time: float) -> bool:
        """Check if scan timeout exceeded"""
        elapsed = time.time() - start_time
        if elapsed > self.config.scan_timeout_seconds:
            logger.warning(f"Archive scan timeout exceeded ({elapsed:.1f}s)")
            return True
        return False
    
    def _scan_zip_archive(self, filepath: Path, depth: int, start_time: float):
        """Scan ZIP archive"""
        from .scanner import ScanResult, ScanAction
        
        try:
            with zipfile.ZipFile(filepath, 'r') as zf:
                # Check if encrypted
                for info in zf.infolist():
                    if info.flag_bits & 0x1:  # Encrypted flag
                        if self.config.block_encrypted_archives:
                            logger.warning(f"Encrypted ZIP archive: {filepath.name}")
                            return ScanResult(
                                blocked=True,
                                action=ScanAction.BLOCK,
                                reason="Encrypted archive not allowed",
                                location=str(filepath)
                            )
                
                # Check member count
                member_count = len(zf.namelist())
                if member_count > self.config.max_members:
                    logger.warning(f"ZIP has too many members: {member_count}")
                    return ScanResult(
                        blocked=True,
                        action=ScanAction.BLOCK,
                        reason=f"Archive has too many files ({member_count})",
                        location=str(filepath)
                    )
                
                # Scan each member
                for member_name in zf.namelist():
                    # Check timeout
                    if self._check_timeout(start_time):
                        return ScanResult(
                            blocked=True,
                            action=ScanAction.BLOCK,
                            reason="Archive scan timeout exceeded",
                            location=str(filepath)
                        )
                    
                    # Skip directories
                    if member_name.endswith('/'):
                        continue
                    
                    info = zf.getinfo(member_name)
                    
                    # Size check
                    if info.file_size > self.max_extract_size:
                        logger.debug(f"Skipping large member: {member_name} ({info.file_size} bytes)")
                        continue
                    
                    # Extract to memory
                    try:
                        content = zf.read(member_name)
                    except Exception as e:
                        logger.error(f"Error extracting {member_name}: {e}")
                        continue
                    
                    # Check if nested archive
                    member_path = Path(member_name)
                    if self.is_archive(member_path):
                        # Would need to write to temp file for nested archive
                        # For now, scan content directly
                        logger.debug(f"Nested archive detected: {member_name}")
                        # Recursive scanning of nested archives would require temp files
                        # Simplified: just scan the bytes
                        result = self.content_scanner.scan_content(content, member_name)
                    else:
                        # Scan file content
                        result = self.content_scanner.scan_content(content, member_name)
                    
                    if result.blocked:
                        result.location = f"{filepath.name}:{member_name}"
                        return result
                
                return ScanResult(
                    blocked=False,
                    action=ScanAction.ALLOW,
                    reason="Archive scan complete, no issues found"
                )
                
        except zipfile.BadZipFile:
            logger.error(f"Invalid ZIP file: {filepath.name}")
            return ScanResult(
                blocked=True,
                action=ScanAction.BLOCK,
                reason="Invalid or corrupted ZIP archive"
            )
    
    def _scan_tar_archive(self, filepath: Path, depth: int, start_time: float):
        """Scan TAR archive (including .tar.gz, .tar.bz2, .tar.xz)"""
        from .scanner import ScanResult, ScanAction
        
        try:
            with tarfile.open(filepath, 'r:*') as tf:
                members = tf.getmembers()
                
                # Check member count
                if len(members) > self.config.max_members:
                    logger.warning(f"TAR has too many members: {len(members)}")
                    return ScanResult(
                        blocked=True,
                        action=ScanAction.BLOCK,
                        reason=f"Archive has too many files ({len(members)})",
                        location=str(filepath)
                    )
                
                # Scan each member
                for member in members:
                    # Check timeout
                    if self._check_timeout(start_time):
                        return ScanResult(
                            blocked=True,
                            action=ScanAction.BLOCK,
                            reason="Archive scan timeout exceeded",
                            location=str(filepath)
                        )
                    
                    # Skip directories and special files
                    if not member.isfile():
                        continue
                    
                    # Size check
                    if member.size > self.max_extract_size:
                        logger.debug(f"Skipping large member: {member.name} ({member.size} bytes)")
                        continue
                    
                    # Extract to memory
                    try:
                        f = tf.extractfile(member)
                        if f:
                            content = f.read()
                            f.close()
                        else:
                            continue
                    except Exception as e:
                        logger.error(f"Error extracting {member.name}: {e}")
                        continue
                    
                    # Scan content
                    result = self.content_scanner.scan_content(content, member.name)
                    
                    if result.blocked:
                        result.location = f"{filepath.name}:{member.name}"
                        return result
                
                return ScanResult(
                    blocked=False,
                    action=ScanAction.ALLOW,
                    reason="Archive scan complete, no issues found"
                )
                
        except tarfile.TarError as e:
            logger.error(f"Invalid TAR file: {filepath.name}: {e}")
            return ScanResult(
                blocked=True,
                action=ScanAction.BLOCK,
                reason="Invalid or corrupted TAR archive"
            )
    
    def _scan_7z_archive(self, filepath: Path, depth: int, start_time: float):
        """Scan 7Z archive"""
        from .scanner import ScanResult, ScanAction
        
        try:
            import py7zr
        except ImportError:
            logger.warning("py7zr not installed, skipping 7z archive")
            return ScanResult(
                blocked=False,
                action=ScanAction.ALLOW,
                reason="7z support not installed"
            )
        
        try:
            with py7zr.SevenZipFile(filepath, 'r') as archive:
                # Check if encrypted
                if archive.password_protected:
                    if self.config.block_encrypted_archives:
                        logger.warning(f"Encrypted 7z archive: {filepath.name}")
                        return ScanResult(
                            blocked=True,
                            action=ScanAction.BLOCK,
                            reason="Encrypted archive not allowed",
                            location=str(filepath)
                        )
                    return ScanResult(
                        blocked=False,
                        action=ScanAction.ALLOW,
                        reason="Encrypted archive (allowed by policy)"
                    )
                
                all_files = archive.getnames()
                
                # Check member count
                if len(all_files) > self.config.max_members:
                    logger.warning(f"7z has too many members: {len(all_files)}")
                    return ScanResult(
                        blocked=True,
                        action=ScanAction.BLOCK,
                        reason=f"Archive has too many files ({len(all_files)})",
                        location=str(filepath)
                    )
                
                # Extract all to memory
                extracted = archive.readall()
                
                for filename, bio in extracted.items():
                    # Check timeout
                    if self._check_timeout(start_time):
                        return ScanResult(
                            blocked=True,
                            action=ScanAction.BLOCK,
                            reason="Archive scan timeout exceeded",
                            location=str(filepath)
                        )
                    
                    content = bio.read()
                    
                    # Size check
                    if len(content) > self.max_extract_size:
                        logger.debug(f"Skipping large member: {filename} ({len(content)} bytes)")
                        continue
                    
                    # Scan content
                    result = self.content_scanner.scan_content(content, filename)
                    
                    if result.blocked:
                        result.location = f"{filepath.name}:{filename}"
                        return result
                
                return ScanResult(
                    blocked=False,
                    action=ScanAction.ALLOW,
                    reason="Archive scan complete, no issues found"
                )
                
        except Exception as e:
            logger.error(f"Error scanning 7z archive {filepath.name}: {e}")
            return ScanResult(
                blocked=True,
                action=ScanAction.BLOCK,
                reason=f"7z archive error: {str(e)}"
            )
    
    def _scan_rar_archive(self, filepath: Path, depth: int, start_time: float):
        """Scan RAR archive"""
        from .scanner import ScanResult, ScanAction
        
        try:
            import rarfile
        except ImportError:
            logger.warning("rarfile not installed, skipping RAR archive")
            return ScanResult(
                blocked=False,
                action=ScanAction.ALLOW,
                reason="RAR support not installed"
            )
        
        try:
            with rarfile.RarFile(filepath, 'r') as rf:
                # Check if encrypted
                if rf.needs_password():
                    if self.config.block_encrypted_archives:
                        logger.warning(f"Encrypted RAR archive: {filepath.name}")
                        return ScanResult(
                            blocked=True,
                            action=ScanAction.BLOCK,
                            reason="Encrypted archive not allowed",
                            location=str(filepath)
                        )
                    return ScanResult(
                        blocked=False,
                        action=ScanAction.ALLOW,
                        reason="Encrypted archive (allowed by policy)"
                    )
                
                members = rf.infolist()
                
                # Check member count
                if len(members) > self.config.max_members:
                    logger.warning(f"RAR has too many members: {len(members)}")
                    return ScanResult(
                        blocked=True,
                        action=ScanAction.BLOCK,
                        reason=f"Archive has too many files ({len(members)})",
                        location=str(filepath)
                    )
                
                # Scan each member
                for member in members:
                    # Check timeout
                    if self._check_timeout(start_time):
                        return ScanResult(
                            blocked=True,
                            action=ScanAction.BLOCK,
                            reason="Archive scan timeout exceeded",
                            location=str(filepath)
                        )
                    
                    # Skip directories
                    if member.isdir():
                        continue
                    
                    # Size check
                    if member.file_size > self.max_extract_size:
                        logger.debug(f"Skipping large member: {member.filename} ({member.file_size} bytes)")
                        continue
                    
                    # Extract to memory
                    try:
                        content = rf.read(member.filename)
                    except Exception as e:
                        logger.error(f"Error extracting {member.filename}: {e}")
                        continue
                    
                    # Scan content
                    result = self.content_scanner.scan_content(content, member.filename)
                    
                    if result.blocked:
                        result.location = f"{filepath.name}:{member.filename}"
                        return result
                
                return ScanResult(
                    blocked=False,
                    action=ScanAction.ALLOW,
                    reason="Archive scan complete, no issues found"
                )
                
        except Exception as e:
            logger.error(f"Error scanning RAR archive {filepath.name}: {e}")
            return ScanResult(
                blocked=True,
                action=ScanAction.BLOCK,
                reason=f"RAR archive error: {str(e)}"
            )
    
    def _scan_compressed_file(self, filepath: Path, compression_type: str, 
                              depth: int, start_time: float) -> 'ScanResult':
        """
        Scan standalone compressed files (.gz, .bz2, .xz).
        
        Args:
            filepath: Path to compressed file
            compression_type: Type of compression (gzip, bzip2, xz)
            depth: Current nesting depth
            start_time: Scan start time
            
        Returns:
            ScanResult with findings
        """
        from ..scanner import ScanResult, ScanAction
        
        try:
            # Decompress to memory
            content = None
            decompressed_name = str(filepath.name).rsplit('.', 1)[0]
            
            if compression_type == 'gzip':
                import gzip
                with gzip.open(filepath, 'rb') as f:
                    # Size check
                    content = f.read(self.max_extract_size + 1)
                    if len(content) > self.max_extract_size:
                        logger.warning(f"Decompressed file too large: {filepath.name}")
                        return ScanResult(
                            blocked=True,
                            action=ScanAction.BLOCK,
                            reason=f"Decompressed file exceeds size limit",
                            location=str(filepath)
                        )
            
            elif compression_type == 'bzip2':
                import bz2
                with bz2.open(filepath, 'rb') as f:
                    content = f.read(self.max_extract_size + 1)
                    if len(content) > self.max_extract_size:
                        logger.warning(f"Decompressed file too large: {filepath.name}")
                        return ScanResult(
                            blocked=True,
                            action=ScanAction.BLOCK,
                            reason=f"Decompressed file exceeds size limit",
                            location=str(filepath)
                        )
            
            elif compression_type == 'xz':
                import lzma
                with lzma.open(filepath, 'rb') as f:
                    content = f.read(self.max_extract_size + 1)
                    if len(content) > self.max_extract_size:
                        logger.warning(f"Decompressed file too large: {filepath.name}")
                        return ScanResult(
                            blocked=True,
                            action=ScanAction.BLOCK,
                            reason=f"Decompressed file exceeds size limit",
                            location=str(filepath)
                        )
            
            if content:
                # Check if decompressed content is an archive
                decompressed_path = Path(decompressed_name)
                if self.is_archive(decompressed_path) and depth < self.config.max_depth:
                    # For nested archives, would need temp file
                    # For now, scan content directly
                    logger.debug(f"Nested archive in compressed file: {decompressed_name}")
                
                # Scan content
                result = self.content_scanner.scan_content(content, decompressed_name)
                if result.blocked:
                    result.location = f"{filepath.name}:{decompressed_name}"
                    return result
            
            return ScanResult(
                blocked=False,
                action=ScanAction.ALLOW,
                reason="Compressed file scan complete"
            )
        
        except Exception as e:
            logger.error(f"Error scanning compressed file {filepath.name}: {e}")
            return ScanResult(
                blocked=True,
                action=ScanAction.BLOCK,
                reason=f"Compressed file error: {str(e)}"
            )


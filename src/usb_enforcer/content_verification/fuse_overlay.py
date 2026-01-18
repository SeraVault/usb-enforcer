"""
FUSE overlay filesystem for content scanning.

Intercepts write operations to scan for sensitive data before
allowing writes to the underlying encrypted USB device.
"""

import os
import errno
import logging
import shutil
import threading
import time
import tempfile
from pathlib import Path
from typing import Optional, Dict
from fuse import FUSE, FuseOSError, Operations

logger = logging.getLogger(__name__)


class ScanProgress:
    """Track scanning progress for a file"""
    
    def __init__(self, filepath: str, total_size: int):
        self.filepath = filepath
        self.total_size = total_size
        self.scanned_size = 0
        self.status = "scanning"  # scanning, blocked, allowed, error
        self.start_time = time.time()
        self.matches = []
        self.scan_complete = False
    
    def update(self, scanned: int):
        """Update progress"""
        self.scanned_size = min(scanned, self.total_size)
    
    def get_progress(self) -> float:
        """Get progress percentage (0-100)"""
        if self.total_size == 0:
            return 100.0
        return (self.scanned_size / self.total_size) * 100.0
    
    def complete(self, blocked: bool, reason: str = ""):
        """Mark scan as complete"""
        self.scan_complete = True
        self.status = "blocked" if blocked else "allowed"
        if blocked:
            self.matches.append(reason)


class ContentScanningFuse(Operations):
    """
    FUSE filesystem that intercepts writes for content scanning.
    
    This provides a transparent overlay that:
    - Passes through all read operations
    - Intercepts write operations for scanning
    - Blocks writes containing sensitive data
    - Reports progress via DBus
    - Maintains full filesystem semantics
    """
    
    def __init__(self, root: str, scanner, archive_scanner, document_scanner,
                 progress_callback=None, blocked_callback=None, is_encrypted=True, config=None):
        """
        Initialize FUSE overlay.
        
        Args:
            root: Real mount point in hidden backing directory (e.g., /media/user/.usb-enforcer-backing/drive)
            scanner: Configured ContentScanner instance
            archive_scanner: ArchiveScanner instance
            document_scanner: DocumentScanner instance
            progress_callback: Callback for progress updates
            blocked_callback: Callback when file is blocked (filepath, reason, patterns)
            is_encrypted: Whether the underlying device is encrypted (LUKS)
            config: ContentScanningConfig instance
        """
        self.root = Path(root)
        self.scanner = scanner
        self.archive_scanner = archive_scanner
        self.document_scanner = document_scanner
        self.progress_callback = progress_callback
        self.blocked_callback = blocked_callback
        self.is_encrypted = is_encrypted
        self.config = config
        self.max_write_bytes = None
        if self.config and getattr(self.config, "max_file_size_mb", None):
            self.max_write_bytes = int(self.config.max_file_size_mb * 1024 * 1024)
        
        # Track write operations - always use temp files (streaming)
        self.file_paths: Dict[int, str] = {}
        self.file_progress: Dict[str, ScanProgress] = {}
        self.temp_paths: Dict[int, str] = {}
        self.temp_fds: Dict[int, int] = {}
        self.temp_sizes: Dict[int, int] = {}
        
        # Statistics
        self.stats = {
            'files_scanned': 0,
            'files_blocked': 0,
            'files_allowed': 0,
            'total_bytes_scanned': 0,
            'patterns_detected': 0,
        }
        self.passthrough_fds = set()
        self.scan_semaphore = None
        if self.config and getattr(self.config, "max_concurrent_scans", None):
            max_scans = max(1, int(self.config.max_concurrent_scans))
            self.scan_semaphore = threading.Semaphore(max_scans)
        
        logger.info(f"FUSE overlay initialized: {root}")
    
    def _full_path(self, partial):
        """Get full path in underlying filesystem"""
        if partial.startswith("/"):
            partial = partial[1:]
        path = os.path.join(self.root, partial)
        return path
    
    def _notify_progress(self, progress: ScanProgress):
        """Notify about scan progress"""
        if self.progress_callback:
            try:
                self.progress_callback(
                    filepath=progress.filepath,
                    progress=progress.get_progress(),
                    status=progress.status,
                    total_size=progress.total_size,
                    scanned_size=progress.scanned_size
                )
            except Exception as e:
                logger.error(f"Error in progress callback: {e}")
    
    # Filesystem methods - pass through reads
    
    def getattr(self, path, fh=None):
        """Get file attributes"""
        full_path = self._full_path(path)
        st = os.lstat(full_path)
        return dict((key, getattr(st, key)) for key in (
            'st_atime', 'st_ctime', 'st_gid', 'st_mode',
            'st_mtime', 'st_nlink', 'st_size', 'st_uid'))
    
    def readdir(self, path, fh):
        """Read directory contents"""
        full_path = self._full_path(path)
        dirents = ['.', '..']
        if os.path.isdir(full_path):
            dirents.extend(os.listdir(full_path))
        return dirents
    
    def read(self, path, length, offset, fh):
        """Read file data - pass through"""
        os.lseek(fh, offset, os.SEEK_SET)
        return os.read(fh, length)
    
    def readlink(self, path):
        """Read symbolic link"""
        pathname = os.readlink(self._full_path(path))
        if pathname.startswith("/"):
            return os.path.relpath(pathname, self.root)
        else:
            return pathname
    
    # Write operations - SCAN BEFORE ALLOWING
    
    def create(self, path, mode, fi=None):
        """Create a new file"""
        full_path = self._full_path(path)
        fh = os.open(full_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        
        # Track this file
        self.file_paths[fh] = path
        
        return fh
    
    def open(self, path, flags):
        """Open a file"""
        full_path = self._full_path(path)
        fh = os.open(full_path, flags)
        
        # Track this file if opened for writing
        if flags & (os.O_WRONLY | os.O_RDWR):
            self.file_paths[fh] = path
        
        return fh
    
    def write(self, path, buf, offset, fh):
        """
        Write file data - STREAM TO TEMP FILE
        
        This is the critical security boundary where we stream writes
        to a temp file for scanning before allowing data to reach the USB device.
        All files use streaming regardless of size for simplicity and safety.
        """
        if fh in self.passthrough_fds:
            try:
                os.lseek(fh, offset, os.SEEK_SET)
                os.write(fh, buf)
                return len(buf)
            except Exception as e:
                logger.error(f"Error writing file: {e}")
                raise FuseOSError(errno.EIO)
        
        # Create temp file on first write
        if fh not in self.temp_paths:
            file_path = self.file_paths.get(fh, path)
            suffix = Path(file_path).suffix if file_path else ""
            temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
            self.temp_paths[fh] = temp_path
            self.temp_fds[fh] = temp_fd
            self.temp_sizes[fh] = 0
            
            # Create progress tracker
            full_path = self._full_path(file_path)
            try:
                # Estimate size from current file or default
                if os.path.exists(full_path):
                    total_size = os.path.getsize(full_path)
                else:
                    total_size = len(buf)  # Initial estimate
                
                progress = ScanProgress(file_path, total_size)
                self.file_progress[file_path] = progress
                self._notify_progress(progress)
            except:
                pass
        
        # Check max file size
        required_len = offset + len(buf)
        if self.max_write_bytes is not None and required_len > self.max_write_bytes:
            action = "block"
            if self.config and getattr(self.config, "oversize_action", None):
                action = self.config.oversize_action
            if action == "allow_unscanned":
                logger.warning(f"⚠️  Oversize file, allowing without scan: {path}")
                # Switch to passthrough mode
                temp_path = self.temp_paths.pop(fh)
                temp_fd = self.temp_fds.pop(fh)
                self.temp_sizes.pop(fh, None)
                self.file_paths.pop(fh, None)
                self.passthrough_fds.add(fh)
                # Copy temp file to real file
                try:
                    os.lseek(temp_fd, 0, os.SEEK_SET)
                    os.lseek(fh, 0, os.SEEK_SET)
                    os.ftruncate(fh, 0)
                    shutil.copyfileobj(os.fdopen(temp_fd, 'rb', closefd=False), 
                                     os.fdopen(fh, 'wb', closefd=False))
                    os.close(temp_fd)
                    os.unlink(temp_path)
                    # Now write the current buffer
                    os.lseek(fh, offset, os.SEEK_SET)
                    os.write(fh, buf)
                except Exception as e:
                    logger.error(f"Error in passthrough: {e}")
                    raise FuseOSError(errno.EIO)
                return len(buf)
            # Block oversized file
            reason = f"File exceeds max size ({self.max_write_bytes} bytes)"
            logger.warning(f"⛔ BLOCKED: {path}: {reason}")
            self.stats['files_blocked'] += 1
            file_path = self.file_paths.get(fh, path)
            if file_path in self.file_progress:
                progress = self.file_progress[file_path]
                progress.complete(blocked=True, reason=reason)
                self._notify_progress(progress)
            if self.blocked_callback:
                try:
                    self.blocked_callback(
                        filepath=file_path,
                        reason=reason,
                        patterns="",
                        match_count=0
                    )
                except Exception as e:
                    logger.error(f"Error in blocked callback: {e}")
            # Clean up
            temp_path = self.temp_paths.pop(fh, None)
            temp_fd = self.temp_fds.pop(fh, None)
            self.temp_sizes.pop(fh, None)
            self.file_paths.pop(fh, None)
            if temp_fd:
                try:
                    os.close(temp_fd)
                    os.unlink(temp_path)
                except Exception:
                    pass
            try:
                os.close(fh)
            except Exception:
                pass
            full_path = self._full_path(path)
            try:
                if os.path.exists(full_path):
                    os.unlink(full_path)
            except Exception as e:
                logger.error(f"Error deleting oversized file: {e}")
            raise FuseOSError(errno.EFBIG)
        
        # Write to temp file
        temp_fd = self.temp_fds[fh]
        try:
            os.lseek(temp_fd, offset, os.SEEK_SET)
            os.write(temp_fd, buf)
            current_size = max(self.temp_sizes.get(fh, 0), required_len)
            self.temp_sizes[fh] = current_size
        except Exception as e:
            logger.error(f"Error writing temp file: {e}")
            raise FuseOSError(errno.EIO)
        
        # Update progress
        file_path = self.file_paths.get(fh, path)
        if file_path in self.file_progress:
            progress = self.file_progress[file_path]
            progress.update(self.temp_sizes[fh])
            self._notify_progress(progress)
        
        return len(buf)
    
    def truncate(self, path, length, fh=None):
        """Truncate file to specified length"""
        full_path = self._full_path(path)
        with open(full_path, 'r+') as f:
            f.truncate(length)
    
    def flush(self, path, fh):
        """Flush file - no-op for now"""
        return 0
    
    def release(self, path, fh):
        """
        Close file - PERFORM FINAL SCAN
        
        When file is closed, scan accumulated writes and either
        commit to disk or block the operation.
        """
        try:
            # Get temp file info
            file_path = self.file_paths.get(fh, path)
            temp_path = self.temp_paths.get(fh)
            temp_fd = self.temp_fds.get(fh)

            if fh in self.passthrough_fds:
                self.passthrough_fds.discard(fh)
                self.file_paths.pop(fh, None)
                return os.close(fh)
            
            if temp_path:
                try:
                    os.lseek(temp_fd, 0, os.SEEK_SET)
                except Exception:
                    pass
                size_hint = self.temp_sizes.get(fh, 0)
                logger.info(f"Scanning {file_path} ({size_hint} bytes)")
                
                # Update progress to scanning
                if file_path in self.file_progress:
                    progress = self.file_progress[file_path]
                    progress.status = "scanning"
                    progress.total_size = size_hint
                    progress.update(size_hint)
                    self._notify_progress(progress)
                
                scan_token = None
                if self.scan_semaphore:
                    scan_token = self.scan_semaphore
                    scan_token.acquire()
                try:
                    # Determine scan method based on file type
                    filename = os.path.basename(path)
                    filepath_obj = Path(filename)
                    scan_path = Path(temp_path)
                    scan_archives = True
                    scan_documents = True
                    if self.config and getattr(self.config, "archives", None):
                        scan_archives = self.config.archives.scan_archives
                    if self.config and getattr(self.config, "documents", None):
                        scan_documents = self.config.documents.scan_documents
                    
                    # Check if it's an archive
                    if scan_archives and self.archive_scanner.is_archive(filepath_obj):
                        logger.debug(f"Scanning as archive: {filename}")
                        result = self.archive_scanner.scan_archive(scan_path)
                    
                    # Check if it's a document
                    elif scan_documents and self.document_scanner.is_document(filepath_obj):
                        logger.debug(f"Scanning as document: {filename}")
                        result = self.document_scanner.scan_document(scan_path)
                    
                    # Regular content scan
                    else:
                        logger.debug(f"Scanning as content: {filename}")
                        result = self.scanner.scan_file(scan_path)
                finally:
                    if scan_token:
                        scan_token.release()
                
                # Update statistics
                self.stats['files_scanned'] += 1
                self.stats['total_bytes_scanned'] += size_hint
                
                # Check if we should enforce based on encryption status
                should_enforce = True
                if self.is_encrypted and self.config:
                    # If device is encrypted and enforce_on_encrypted_devices is False, allow it
                    if not self.config.enforce_on_encrypted_devices:
                        should_enforce = False
                        logger.info(f"✓ ALLOWED on encrypted device (enforce_on_encrypted_devices=false): {file_path}")
                        if result.matches:
                            logger.info(f"   Detected patterns: {', '.join(m.pattern_name for m in result.matches)} - but allowing due to encryption")
                
                if result.blocked and should_enforce:
                    # BLOCK: Don't write to disk
                    self.stats['files_blocked'] += 1
                    self.stats['patterns_detected'] += len(result.matches)
                    
                    logger.warning(f"⛔ BLOCKED: {file_path}: {result.reason}")
                    
                    # Collect pattern information for notification
                    pattern_summary = []
                    for match in result.matches:
                        pattern_summary.append(f"{match.pattern_name} ({match.pattern_category})")
                    patterns_text = ", ".join(set(pattern_summary))  # Deduplicate
                    
                    # Update progress
                    if file_path in self.file_progress:
                        progress = self.file_progress[file_path]
                        progress.complete(blocked=True, reason=result.reason)
                        self._notify_progress(progress)
                    
                    # Send blocked notification with details
                    if self.blocked_callback:
                        try:
                            self.blocked_callback(
                                filepath=file_path,
                                reason=result.reason,
                                patterns=patterns_text,
                                match_count=len(result.matches)
                            )
                        except Exception as e:
                            logger.error(f"Error in blocked callback: {e}")
                    
                    # Clean up temp file
                    if fh in self.file_paths:
                        del self.file_paths[fh]
                    temp_path = self.temp_paths.pop(fh, None)
                    temp_fd = self.temp_fds.pop(fh, None)
                    self.temp_sizes.pop(fh, None)
                    if temp_path:
                        try:
                            if temp_fd is not None:
                                os.close(temp_fd)
                            os.unlink(temp_path)
                        except Exception:
                            pass
                    
                    # Close file handle
                    try:
                        os.close(fh)
                    except:
                        pass
                    
                    # Delete the file
                    full_path = self._full_path(path)
                    try:
                        if os.path.exists(full_path):
                            os.unlink(full_path)
                    except Exception as e:
                        logger.error(f"Error deleting blocked file: {e}")
                    
                    # Return error
                    raise FuseOSError(errno.EACCES)
                
                else:
                    # ALLOW: Write temp file to disk
                    self.stats['files_allowed'] += 1
                    
                    logger.info(f"✅ ALLOWED: {file_path}")
                    
                    # Update progress
                    if file_path in self.file_progress:
                        progress = self.file_progress[file_path]
                        progress.complete(blocked=False)
                        self._notify_progress(progress)
                    
                    # Write temp file to real file
                    try:
                        os.lseek(fh, 0, os.SEEK_SET)
                        os.ftruncate(fh, 0)
                        with open(temp_path, "rb") as src:
                            while True:
                                chunk = src.read(1024 * 1024)
                                if not chunk:
                                    break
                                os.write(fh, chunk)
                    except Exception as e:
                        logger.error(f"Error writing file: {e}")
                        raise FuseOSError(errno.EIO)
                    
                    # Clean up temp file
                    if fh in self.file_paths:
                        del self.file_paths[fh]
                    temp_path_cleanup = self.temp_paths.pop(fh, None)
                    temp_fd_cleanup = self.temp_fds.pop(fh, None)
                    self.temp_sizes.pop(fh, None)
                    if temp_path_cleanup:
                        try:
                            if temp_fd_cleanup is not None:
                                os.close(temp_fd_cleanup)
                            os.unlink(temp_path_cleanup)
                        except Exception:
                            pass
            
            # Close file handle
            return os.close(fh)
            
        except FuseOSError:
            raise
        except Exception as e:
            logger.error(f"Error in release: {e}", exc_info=True)
            raise FuseOSError(errno.EIO)
    
    # Additional required methods (pass-through)
    
    def chmod(self, path, mode):
        full_path = self._full_path(path)
        return os.chmod(full_path, mode)
    
    def chown(self, path, uid, gid):
        full_path = self._full_path(path)
        return os.chown(full_path, uid, gid)
    
    def mkdir(self, path, mode):
        full_path = self._full_path(path)
        return os.mkdir(full_path, mode)
    
    def rmdir(self, path):
        full_path = self._full_path(path)
        return os.rmdir(full_path)
    
    def unlink(self, path):
        full_path = self._full_path(path)
        return os.unlink(full_path)
    
    def symlink(self, name, target):
        return os.symlink(target, self._full_path(name))
    
    def rename(self, old, new):
        return os.rename(self._full_path(old), self._full_path(new))
    
    def link(self, target, name):
        return os.link(self._full_path(name), self._full_path(target))
    
    def utimens(self, path, times=None):
        full_path = self._full_path(path)
        return os.utime(full_path, times)
    
    def statfs(self, path):
        full_path = self._full_path(path)
        stv = os.statvfs(full_path)
        return dict((key, getattr(stv, key)) for key in (
            'f_bavail', 'f_bfree', 'f_blocks', 'f_bsize',
            'f_favail', 'f_ffree', 'f_files', 'f_flag',
            'f_frsize', 'f_namemax'))
    
    def get_statistics(self):
        """Get scanning statistics"""
        return self.stats.copy()


class FuseManager:
    """
    Manages FUSE mounts with content scanning.
    
    Handles mounting/unmounting and progress notifications.
    """
    
    def __init__(self, scanner, archive_scanner, document_scanner, config=None):
        """
        Initialize FUSE manager.
        
        Args:
            scanner: ContentScanner instance
            archive_scanner: ArchiveScanner instance
            document_scanner: DocumentScanner instance
            config: ContentScanningConfig instance
        """
        self.scanner = scanner
        self.archive_scanner = archive_scanner
        self.document_scanner = document_scanner
        self.config = config
        self.mounts = {}  # mount_point -> (fuse_thread, fuse_ops)
        self.progress_handlers = []
        self.blocked_handlers = []
        
        logger.info("FUSE manager initialized")
    
    def add_progress_handler(self, handler):
        """Add a progress notification handler"""
        self.progress_handlers.append(handler)
    
    def add_blocked_handler(self, handler):
        """Add a blocked file notification handler"""
        self.blocked_handlers.append(handler)
    
    def _progress_callback(self, **kwargs):
        """Forward progress to all handlers"""
        for handler in self.progress_handlers:
            try:
                handler(**kwargs)
            except Exception as e:
                logger.error(f"Error in progress handler: {e}")
    
    def _blocked_callback(self, **kwargs):
        """Forward blocked notifications to all handlers"""
        for handler in self.blocked_handlers:
            try:
                handler(**kwargs)
            except Exception as e:
                logger.error(f"Error in blocked handler: {e}")
    
    def mount(
        self,
        device_path: str,
        mount_point: str,
        is_encrypted: bool = True,
        source_is_mount: bool = False,
    ) -> bool:
        """
        Mount USB device with content scanning FUSE overlay.
        
        Args:
            device_path: Underlying device path (e.g., /dev/mapper/luks-xxx) or existing mount path
            mount_point: Where to expose FUSE overlay
            is_encrypted: Whether the device is LUKS encrypted
            source_is_mount: Whether device_path is already a mounted path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if source_is_mount:
                real_mount = device_path
            else:
                # Create real mount point in a hidden directory
                # Extract the parent directory and drive name
                parent_dir = os.path.dirname(mount_point)
                drive_name = os.path.basename(mount_point)
                
                # Create hidden backing directory in parent (e.g., /run/media/user/.usb-enforcer-backing)
                hidden_base = os.path.join(parent_dir, '.usb-enforcer-backing')
                os.makedirs(hidden_base, exist_ok=True)
                
                # Mount actual device to hidden location
                real_mount = os.path.join(hidden_base, drive_name)
                os.makedirs(real_mount, exist_ok=True)
                
                import subprocess
                result = subprocess.run(
                    ['mount', device_path, real_mount],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode != 0:
                    logger.error(f"Failed to mount device: {result.stderr}")
                    return False
            
            # Create FUSE mount point
            os.makedirs(mount_point, exist_ok=True)
            
            # Create FUSE operations
            fuse_ops = ContentScanningFuse(
                real_mount,
                self.scanner,
                self.archive_scanner,
                self.document_scanner,
                progress_callback=self._progress_callback,
                blocked_callback=self._blocked_callback,
                is_encrypted=is_encrypted,
                config=self.config
            )
            
            # Mount FUSE overlay in background thread
            def run_fuse():
                try:
                    FUSE(
                        fuse_ops,
                        mount_point,
                        nothreads=False,
                        foreground=True,
                        allow_other=True
                    )
                except Exception as e:
                    logger.error(f"FUSE error: {e}", exc_info=True)
            
            fuse_thread = threading.Thread(target=run_fuse, daemon=True)
            fuse_thread.start()
            
            # Store mount info
            self.mounts[mount_point] = (fuse_thread, fuse_ops, real_mount)
            
            logger.info(f"✅ Content scanning FUSE mounted: {mount_point}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to mount FUSE overlay: {e}", exc_info=True)
            return False
    
    def unmount(self, mount_point: str) -> bool:
        """
        Unmount FUSE overlay.
        
        Args:
            mount_point: Mount point to unmount
            
        Returns:
            True if successful
        """
        try:
            if mount_point not in self.mounts:
                return False
            
            _, _, real_mount = self.mounts[mount_point]
            
            # Unmount FUSE
            import subprocess
            fusermount_cmd = shutil.which("fusermount3") or shutil.which("fusermount") or "fusermount"
            subprocess.run([fusermount_cmd, '-u', mount_point])
            
            # Unmount real device
            subprocess.run(['umount', real_mount])
            
            # Clean up mount directories
            try:
                os.rmdir(real_mount)
                # Try to remove parent hidden directory if empty
                hidden_base = os.path.dirname(real_mount)
                if os.path.basename(hidden_base) == '.usb-enforcer-backing':
                    try:
                        os.rmdir(hidden_base)
                    except OSError:
                        pass  # Directory not empty or other error
            except:
                pass
            
            del self.mounts[mount_point]
            
            logger.info(f"Unmounted: {mount_point}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unmount: {e}")
            return False
    
    def get_statistics(self, mount_point: str):
        """Get statistics for a mount point"""
        if mount_point in self.mounts:
            _, fuse_ops, _ = self.mounts[mount_point]
            return fuse_ops.get_statistics()
        return None

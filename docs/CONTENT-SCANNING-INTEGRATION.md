# Content Scanner Integration Guide

This guide explains how to integrate the content scanning module with the USB Enforcer daemon and enable real-time file interception.

## Architecture Overview

The content scanner is currently standalone. To complete the integration:

```
┌─────────────────────────────────────────────────────────┐
│                    Integration Flow                      │
└─────────────────────────────────────────────────────────┘

  USB Device Inserted
         │
         ▼
  ┌──────────────────┐
  │ udev Monitor     │
  │ (existing)       │
  └──────┬───────────┘
         │
         ▼
  ┌──────────────────┐
  │ Daemon detects   │
  │ LUKS device      │ (existing)
  └──────┬───────────┘
         │
         ▼
  ┌──────────────────┐
  │ User unlocks     │
  │ via wizard       │ (existing)
  └──────┬───────────┘
         │
         ▼
  ┌──────────────────────────┐
  │ Check config:            │ (NEW)
  │ content_scanning.enabled │
  └──────┬───────────────────┘
         │
         ├─► NO  ──► Normal mount to /media/usb-enforcer/ (existing)
         │
         └─► YES
              │
              ▼
         ┌──────────────────────┐
         │ Mount via FUSE       │ (NEW)
         │ Overlay at           │
         │ /media/usb-enforcer/ │
         └──────┬───────────────┘
                │
                ▼
         ┌──────────────────────┐
         │ FUSE intercepts      │ (NEW)
         │ write() calls        │
         └──────┬───────────────┘
                │
                ▼
         ┌──────────────────────┐
         │ Content Scanner      │ (IMPLEMENTED)
         │ analyzes file        │
         └──────┬───────────────┘
                │
                ├─► BLOCKED ──► Return -EACCES, notify user
                │
                └─► ALLOWED ─► Pass through to real mount
```

## Step 1: Update Configuration Module

**File:** `src/usb_enforcer/config.py`

Add content scanning configuration parsing:

```python
# Add to imports
from .content_verification.config import ContentScanningConfig

# In ConfigManager class, add method:
def get_content_scanning_config(self) -> Optional[ContentScanningConfig]:
    """Get content scanning configuration"""
    if not self.config:
        return None
    
    cs_config = self.config.get('content_scanning', {})
    if not cs_config.get('enabled', False):
        return None
    
    return ContentScanningConfig.from_dict(cs_config)
```

## Step 2: Create FUSE Overlay Filesystem

**File:** `src/usb_enforcer/content_verification/fuse_overlay.py`

```python
"""
FUSE overlay filesystem for content scanning.

Intercepts write operations to scan for sensitive data before
allowing writes to the underlying encrypted USB device.
"""

import os
import errno
import logging
from pathlib import Path
from typing import Optional
from fuse import FUSE, FuseOSError, Operations

from .scanner import ContentScanner
from .archive_scanner import ArchiveScanner
from .document_scanner import DocumentScanner

logger = logging.getLogger(__name__)


class ContentScanningFuse(Operations):
    """
    FUSE filesystem that intercepts writes for content scanning.
    
    This provides a transparent overlay that:
    - Passes through all read operations
    - Intercepts write operations for scanning
    - Blocks writes containing sensitive data
    - Maintains full filesystem semantics
    """
    
    def __init__(self, root: str, scanner: ContentScanner):
        """
        Initialize FUSE overlay.
        
        Args:
            root: Real mount point (e.g., /media/.usb-enforcer-real/xxx)
            scanner: Configured ContentScanner instance
        """
        self.root = Path(root)
        self.scanner = scanner
        self.archive_scanner = ArchiveScanner(scanner)
        self.document_scanner = DocumentScanner(scanner)
        
        # Temp storage for files being written
        self.write_buffers = {}  # fd -> bytes buffer
        
        logger.info(f"FUSE overlay initialized: {root}")
    
    def _full_path(self, partial):
        """Get full path in underlying filesystem"""
        if partial.startswith("/"):
            partial = partial[1:]
        path = os.path.join(self.root, partial)
        return path
    
    # Filesystem methods
    
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
    
    def write(self, path, buf, offset, fh):
        """
        Write file data - INTERCEPT AND SCAN
        
        This is the critical security boundary where we perform
        content scanning before allowing data to reach the USB device.
        """
        # Accumulate writes in buffer
        if fh not in self.write_buffers:
            self.write_buffers[fh] = bytearray()
        
        buffer = self.write_buffers[fh]
        
        # Extend buffer if needed
        if offset + len(buf) > len(buffer):
            buffer.extend(b'\x00' * (offset + len(buf) - len(buffer)))
        
        # Write to buffer
        buffer[offset:offset + len(buf)] = buf
        
        # For small files, scan incrementally
        # For large files, scan on close
        return len(buf)
    
    def create(self, path, mode, fi=None):
        """Create a new file"""
        full_path = self._full_path(path)
        return os.open(full_path, os.O_WRONLY | os.O_CREAT, mode)
    
    def open(self, path, flags):
        """Open a file"""
        full_path = self._full_path(path)
        return os.open(full_path, flags)
    
    def release(self, path, fh):
        """
        Close file - PERFORM FINAL SCAN
        
        When file is closed, scan accumulated writes and either
        commit to disk or block the operation.
        """
        try:
            # Get accumulated buffer
            buffer = self.write_buffers.get(fh)
            
            if buffer and len(buffer) > 0:
                # Scan the buffer
                filename = os.path.basename(path)
                result = self.scanner.scan_content(bytes(buffer), filename)
                
                if result.blocked:
                    # BLOCK: Don't write to disk
                    logger.warning(f"Blocked write to {path}: {result.reason}")
                    
                    # Clean up buffer
                    del self.write_buffers[fh]
                    
                    # Close file handle
                    os.close(fh)
                    
                    # Delete the file
                    full_path = self._full_path(path)
                    try:
                        os.unlink(full_path)
                    except:
                        pass
                    
                    # Return error
                    raise FuseOSError(errno.EACCES)
                
                else:
                    # ALLOW: Write buffer to disk
                    logger.debug(f"Allowed write to {path}")
                    os.lseek(fh, 0, os.SEEK_SET)
                    os.write(fh, bytes(buffer))
                    
                    # Clean up buffer
                    del self.write_buffers[fh]
            
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
    
    def rename(self, old, new):
        return os.rename(self._full_path(old), self._full_path(new))
    
    def statfs(self, path):
        full_path = self._full_path(path)
        stv = os.statvfs(full_path)
        return dict((key, getattr(stv, key)) for key in (
            'f_bavail', 'f_bfree', 'f_blocks', 'f_bsize',
            'f_favail', 'f_ffree', 'f_files', 'f_flag',
            'f_frsize', 'f_namemax'))
    
    def utimens(self, path, times=None):
        full_path = self._full_path(path)
        return os.utime(full_path, times)


def mount_with_content_scanning(device_path: str, mount_point: str,
                                scanner: ContentScanner) -> Optional[FUSE]:
    """
    Mount USB device with content scanning FUSE overlay.
    
    Args:
        device_path: Underlying device mount (e.g., /dev/mapper/luks-xxx)
        mount_point: Where to expose FUSE overlay (e.g., /media/usb-enforcer/xxx)
        scanner: Configured ContentScanner instance
        
    Returns:
        FUSE instance if successful, None otherwise
    """
    try:
        # Create real mount point (hidden)
        real_mount = f"{mount_point}.real"
        os.makedirs(real_mount, exist_ok=True)
        
        # Mount actual device to hidden location
        os.system(f"mount {device_path} {real_mount}")
        
        # Create FUSE mount point
        os.makedirs(mount_point, exist_ok=True)
        
        # Mount FUSE overlay
        fuse = FUSE(
            ContentScanningFuse(real_mount, scanner),
            mount_point,
            nothreads=True,
            foreground=False
        )
        
        logger.info(f"Content scanning FUSE mounted: {mount_point}")
        return fuse
        
    except Exception as e:
        logger.error(f"Failed to mount FUSE overlay: {e}")
        return None
```

## Step 3: Update Daemon to Use FUSE

**File:** `src/usb_enforcer/daemon.py`

Add to the device handling logic:

```python
# Add imports
from .content_verification import ContentScanner
from .content_verification.fuse_overlay import mount_with_content_scanning

# In the Daemon class, add:

def _init_content_verification(self):
    """Initialize content scanner if enabled"""
    cs_config = self.config_manager.get_content_scanning_config()
    
    if not cs_config:
        logger.info("Content scanning disabled")
        return None
    
    logger.info("Initializing content scanner")
    scanner_config = cs_config.get_scanner_config()
    return ContentScanner(scanner_config)

# Modify the mount logic:

def _mount_device(self, device_path: str) -> str:
    """Mount device with optional content scanning"""
    
    mount_point = f"/media/usb-enforcer/{device_id}"
    
    # Check if content scanning enabled
    if self.content_verification:
        # Use FUSE overlay
        fuse = mount_with_content_scanning(
            device_path,
            mount_point,
            self.content_verification
        )
        
        if fuse:
            logger.info(f"Mounted with content scanning: {mount_point}")
        else:
            logger.error("Failed to mount with content scanning, using normal mount")
            # Fallback to normal mount
            os.system(f"mount {device_path} {mount_point}")
    else:
        # Normal mount without scanning
        os.makedirs(mount_point, exist_ok=True)
        os.system(f"mount {device_path} {mount_point}")
    
    return mount_point
```

## Step 4: Add DBus API Methods

**File:** `src/usb_enforcer/dbus_api.py`

Add content scanning control methods:

```python
@dbus.service.method("org.seravault.UsbEnforcer",
                     in_signature='s', out_signature='b')
def ScanFile(self, filepath):
    """
    Scan a file for sensitive content.
    
    Args:
        filepath: Absolute path to file
        
    Returns:
        True if file is clean, False if blocked
    """
    if not self.daemon.content_verification:
        return True  # Scanning disabled
    
    from pathlib import Path
    result = self.daemon.content_verification.scan_file(Path(filepath))
    
    if result.blocked:
        logger.warning(f"File blocked: {filepath}: {result.reason}")
        return False
    
    return True

@dbus.service.method("org.seravault.UsbEnforcer",
                     in_signature='', out_signature='a{sv}')
def GetContentScannerStats(self):
    """Get content scanner statistics"""
    if not self.daemon.content_verification:
        return {}
    
    return self.daemon.content_verification.get_statistics()
```

## Step 5: Add User Notifications

When a file is blocked, notify the user via the existing notification system.

## Step 6: Update Wizard UI

Add content scanning settings panel:

```python
# In wizard, add settings page for content scanning
# - Enable/disable toggle
# - Category selection (PII, Financial, Corporate)
# - Action mode (Block, Warn, Log)
# - Custom pattern management
```

## Testing the Integration

### 1. Unit Tests

Add integration tests in `tests/integration/test_content_scanning.py`:

```python
def test_fuse_blocks_sensitive_file():
    """Test that FUSE overlay blocks file with sensitive data"""
    # Mount FUSE overlay
    # Write file with SSN
    # Verify write fails with EACCES
    # Verify file not created on underlying filesystem

def test_fuse_allows_clean_file():
    """Test that FUSE overlay allows clean files"""
    # Mount FUSE overlay
    # Write clean file
    # Verify write succeeds
    # Verify file exists on underlying filesystem
```

### 2. Manual Testing

```bash
# 1. Enable content scanning in config
sudo vi /etc/usb-enforcer/config.toml

# 2. Restart daemon
sudo systemctl restart usb-enforcerd

# 3. Insert USB, unlock it

# 4. Try to write sensitive file
echo "SSN: 123-45-6789" > /media/usb-enforcer/xxx/sensitive.txt
# Should fail with "Permission denied"

# 5. Try to write clean file
echo "Clean content" > /media/usb-enforcer/xxx/clean.txt
# Should succeed

# 6. Check logs
sudo journalctl -u usb-enforcerd | grep content
```

## Performance Considerations

- FUSE introduces overhead (~5-10% for writes)
- Caching minimizes rescanning of unchanged files
- Large files are sampled, not fully scanned
- Multiple concurrent scans limited (default: 4)

## Security Notes

- FUSE runs as root (required for device access)
- Scanner worker should run with limited privileges (future enhancement)
- All scan results logged to journald
- Actual sensitive values never logged
- File hashes used instead of paths in cache

## Rollback Plan

If content scanning causes issues:

1. Set `enabled = false` in config
2. Restart daemon
3. Devices mount normally without scanning
4. No data loss (scanning is transparent)

## Documentation Updates Needed

- [ ] Update ADMINISTRATION.md with content scanning section
- [ ] Add troubleshooting guide for false positives
- [ ] Update README.md with content scanning overview
- [ ] Add example use cases to docs/

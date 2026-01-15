"""
USB Content Verification Module

Handles real-time content scanning of files being written to USB devices:
- Pattern-based detection (SSN, credit cards, API keys, etc.)
- Document text extraction (PDF, DOCX, XLSX, PPTX, ODF)
- Archive scanning (ZIP, TAR, 7Z, RAR)
- N-gram and entropy analysis
- FUSE filesystem overlay for write interception
- GUI notifications with progress tracking
"""

from .scanner import ContentScanner, ScanResult
from .patterns import PatternLibrary, PatternMatch, PatternCategory
from .config import ContentScanningConfig
from .fuse_overlay import FuseManager, ContentScanningFuse
from .notifications import ScanProgressNotifier, create_notification_app

__all__ = [
    'ContentScanner',
    'ScanResult',
    'PatternLibrary',
    'PatternMatch',
    'PatternCategory',
    'ContentScanningConfig',
    'FuseManager',
    'ContentScanningFuse',
    'ScanProgressNotifier',
    'create_notification_app',
]

__version__ = '1.0.0'

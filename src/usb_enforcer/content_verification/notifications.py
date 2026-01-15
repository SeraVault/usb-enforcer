"""
GUI notifications for content scanning progress.

Displays desktop notifications with progress bars when files are being scanned.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ScanNotificationWindow(Gtk.ApplicationWindow):
    """
    Floating notification window showing scan progress.
    
    Displays when files are being scanned with progress bar and status.
    """
    
    def __init__(self, application):
        super().__init__(application=application, title="USB Enforcer - Scanning")
        
        self.set_default_size(400, 200)
        self.set_decorated(True)
        self.set_deletable(False)
        
        # Main box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<b>Scanning File for Sensitive Data</b>")
        title.set_halign(Gtk.Align.START)
        main_box.append(title)
        
        # File name label
        self.filename_label = Gtk.Label()
        self.filename_label.set_halign(Gtk.Align.START)
        self.filename_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        self.filename_label.set_max_width_chars(50)
        main_box.append(self.filename_label)
        
        # Progress bar
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        main_box.append(self.progress_bar)
        
        # Status label
        self.status_label = Gtk.Label()
        self.status_label.set_halign(Gtk.Align.START)
        main_box.append(self.status_label)
        
        # Details expander
        self.details_expander = Gtk.Expander()
        self.details_expander.set_label("Details")
        
        details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        details_box.set_margin_top(6)
        
        self.size_label = Gtk.Label()
        self.size_label.set_halign(Gtk.Align.START)
        details_box.append(self.size_label)
        
        self.speed_label = Gtk.Label()
        self.speed_label.set_halign(Gtk.Align.START)
        details_box.append(self.speed_label)
        
        self.patterns_label = Gtk.Label()
        self.patterns_label.set_halign(Gtk.Align.START)
        details_box.append(self.patterns_label)
        
        self.details_expander.set_child(details_box)
        main_box.append(self.details_expander)
        
        # Close button (only shown when complete)
        self.close_button = Gtk.Button(label="Close")
        self.close_button.connect("clicked", lambda _: self.close())
        self.close_button.set_visible(False)
        main_box.append(self.close_button)
        
        self.set_child(main_box)
        
        # State
        self.start_time = time.time()
        self.last_update = time.time()
        self.last_scanned_size = 0
    
    def update_progress(self, filename: str, progress: float, status: str,
                       total_size: int, scanned_size: int):
        """
        Update progress display.
        
        Args:
            filename: Name of file being scanned
            progress: Progress percentage (0-100)
            status: Status string (scanning, blocked, allowed, error)
            total_size: Total file size in bytes
            scanned_size: Bytes scanned so far
        """
        # Update filename
        self.filename_label.set_text(filename)
        
        # Update progress bar
        self.progress_bar.set_fraction(progress / 100.0)
        self.progress_bar.set_text(f"{progress:.1f}%")
        
        # Update status
        status_icons = {
            'scanning': '🔍',
            'blocked': '⛔',
            'allowed': '✅',
            'error': '❌'
        }
        icon = status_icons.get(status, '⏳')
        
        status_text = {
            'scanning': 'Scanning for sensitive data...',
            'blocked': 'BLOCKED - Contains sensitive data',
            'allowed': 'Allowed - No sensitive data detected',
            'error': 'Error during scanning'
        }
        text = status_text.get(status, status)
        
        self.status_label.set_markup(f"{icon} <b>{text}</b>")
        
        # Update size info
        self.size_label.set_text(
            f"Size: {self._format_bytes(scanned_size)} / {self._format_bytes(total_size)}"
        )
        
        # Calculate speed
        now = time.time()
        elapsed = now - self.last_update
        if elapsed > 0:
            bytes_per_sec = (scanned_size - self.last_scanned_size) / elapsed
            self.speed_label.set_text(f"Speed: {self._format_bytes(bytes_per_sec)}/s")
        
        self.last_update = now
        self.last_scanned_size = scanned_size
        
        # Show close button if complete
        if status in ('blocked', 'allowed', 'error'):
            self.close_button.set_visible(True)
            
            # Auto-close after a few seconds if allowed
            if status == 'allowed':
                GLib.timeout_add_seconds(3, self.close)
    
    def set_patterns_checked(self, count: int):
        """Set number of patterns checked"""
        self.patterns_label.set_text(f"Patterns checked: {count}")
    
    def _format_bytes(self, bytes_val: int) -> str:
        """Format bytes as human-readable string"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f} TB"


class ScanProgressNotifier:
    """
    Manages scan progress notifications.
    
    Creates and updates notification windows for active scans.
    """
    
    def __init__(self, application):
        """
        Initialize notifier.
        
        Args:
            application: Gtk.Application instance
        """
        self.application = application
        self.active_windows: Dict[str, ScanNotificationWindow] = {}
        
        logger.info("Scan progress notifier initialized")
    
    def show_scan_progress(self, filepath: str, progress: float, status: str,
                          total_size: int, scanned_size: int):
        """
        Show or update scan progress notification.
        
        Args:
            filepath: Path to file being scanned
            progress: Progress percentage
            status: Scan status
            total_size: Total file size
            scanned_size: Bytes scanned
        """
        # Get or create window for this file
        if filepath not in self.active_windows:
            window = ScanNotificationWindow(self.application)
            window.connect("close-request", lambda w: self._on_window_closed(filepath))
            self.active_windows[filepath] = window
            window.present()
        else:
            window = self.active_windows[filepath]
        
        # Update progress
        import os
        filename = os.path.basename(filepath)
        window.update_progress(filename, progress, status, total_size, scanned_size)
        
        # Remove window if complete and allowed
        if status == 'allowed':
            # Will auto-close via timeout in window
            pass
    
    def _on_window_closed(self, filepath: str):
        """Handle window close"""
        if filepath in self.active_windows:
            del self.active_windows[filepath]
    
    def hide_scan_progress(self, filepath: str):
        """Hide scan progress for a file"""
        if filepath in self.active_windows:
            window = self.active_windows[filepath]
            window.close()
            del self.active_windows[filepath]


class ScanNotificationService:
    """
    DBus service for scan notifications.
    
    Allows daemon to trigger GUI notifications.
    """
    
    def __init__(self, notifier: ScanProgressNotifier):
        """
        Initialize notification service.
        
        Args:
            notifier: ScanProgressNotifier instance
        """
        self.notifier = notifier
        
        # Send desktop notifications for blocked files
        self.notification_app = None
        try:
            self.notification_app = Gio.Application.get_default()
        except:
            pass
        
        logger.info("Scan notification service initialized")
    
    def notify_scan_progress(self, filepath: str, progress: float, status: str,
                            total_size: int, scanned_size: int):
        """Forward progress to notifier"""
        GLib.idle_add(
            self.notifier.show_scan_progress,
            filepath, progress, status, total_size, scanned_size
        )
    
    def notify_blocked(self, filepath: str, reason: str, patterns: str = "", match_count: int = 0):
        """
        Send urgent notification that file was blocked.
        
        Args:
            filepath: Path to blocked file
            reason: Reason for blocking
            patterns: Comma-separated list of detected patterns
            match_count: Number of sensitive data matches found
        """
        try:
            import os
            filename = os.path.basename(filepath)
            
            # Create detailed notification
            notification = Gio.Notification.new("🚫 USB File Blocked - Sensitive Data Detected")
            
            # Build detailed message
            body_parts = [
                f"File: {filename}",
                f"",
                f"❌ This file was prevented from being written to your USB drive.",
                f"",
                f"🔍 Detected: {match_count} instance(s) of sensitive data",
            ]
            
            if patterns:
                body_parts.append(f"📋 Patterns found: {patterns}")
            
            body_parts.extend([
                f"",
                f"⚠️  Writing files with sensitive data to USB drives is prohibited by policy.",
                f"Please remove sensitive information before copying to removable media."
            ])
            
            notification.set_body("\n".join(body_parts))
            notification.set_priority(Gio.NotificationPriority.URGENT)
            
            if self.notification_app:
                self.notification_app.send_notification("blocked-file", notification)
            
            logger.warning(f"Sent BLOCKED notification: {filename} - {patterns}")
        except Exception as e:
            logger.error(f"Failed to send blocked notification: {e}")
    
    def notify_allowed(self, filepath: str):
        """Send notification that file was allowed"""
        # Only log, don't send notification for allowed files
        logger.debug(f"File allowed: {filepath}")


def create_notification_app() -> Gtk.Application:
    """
    Create GTK application for scan notifications.
    
    Returns:
        Configured Gtk.Application
    """
    app = Gtk.Application(
        application_id='org.seravault.UsbEnforcerNotifications',
        flags=Gio.ApplicationFlags.FLAGS_NONE
    )
    
    notifier = ScanProgressNotifier(app)
    service = ScanNotificationService(notifier)
    
    # Store references
    app.notifier = notifier
    app.service = service
    
    return app

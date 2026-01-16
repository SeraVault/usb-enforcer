from __future__ import annotations

import argparse
import errno
import json
import logging
import os
import pwd
import grp
import secrets
import signal
import socket
import stat
import subprocess
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

import pyudev

from . import config as config_module, constants, dbus_api, logging_utils
from .encryption import classify, crypto_engine, enforcer, udev_monitor

try:
    from gi.repository import GLib  # type: ignore
except Exception:  # pragma: no cover
    GLib = None

# Content verification imports
try:
    from .content_verification.scanner import ContentScanner
    from .content_verification.config import ContentScanningConfig
    from .content_verification.fuse_overlay import FuseManager
    from .content_verification.archive_scanner import ArchiveScanner
    from .content_verification.document_scanner import DocumentScanner
    CONTENT_VERIFICATION_AVAILABLE = True
except ImportError:
    CONTENT_VERIFICATION_AVAILABLE = False


class Daemon:
    def __init__(self, config_path=None):
        self.config = config_module.Config.load(config_path)
        self.logger = logging_utils.setup_logging()
        self.devices: Dict[str, Dict[str, str]] = {}
        self._stop_event = threading.Event()
        self.dbus_service = None
        self._dbus_loop = None
        self._bypass_enforcement: Set[str] = set()
        self._udev_context = pyudev.Context()
        self._secret_socket_path = "/run/usb-enforcer.sock"
        self._secret_socket: Optional[socket.socket] = None
        self._secret_store: Dict[str, Tuple[str, str]] = {}  # token -> (op, passphrase)
        self._secret_lock = threading.Lock()
        
        # Content scanning support
        self.content_scanner: Optional[ContentScanner] = None
        self.fuse_manager: Optional[FuseManager] = None
        self._init_content_scanner()

    def _emit_event(self, fields: Dict[str, str]) -> None:
        if self.dbus_service:
            self.dbus_service.emit_event(fields)

    def _log_event(self, message: str, fields: Dict[str, str]) -> None:
        logging_utils.log_structured(self.logger, message, fields)
        self._emit_event(fields)
    
    def _init_content_scanner(self) -> None:
        """Initialize content scanner if enabled in config"""
        if not CONTENT_VERIFICATION_AVAILABLE:
            self.logger.debug("Content verification module not available")
            return
        
        # Check if content scanning is enabled
        content_config = getattr(self.config, 'content_scanning', None)
        if not content_config or not getattr(content_config, 'enabled', False):
            self.logger.info("Content scanning disabled in config")
            return
        
        try:
            # Initialize scanner with dict config
            scanner_config = content_config.get_scanner_config()
            self.content_scanner = ContentScanner(scanner_config)
            self.logger.info("Content scanner initialized")
            
            # Initialize archive and document scanners
            archive_scanner = ArchiveScanner(
                content_scanner=self.content_scanner,
                config=content_config.archives
            )
            document_scanner = DocumentScanner(
                content_scanner=self.content_scanner
            )
            
            # Initialize FUSE manager for overlay mounting
            self.fuse_manager = FuseManager(
                scanner=self.content_scanner,
                archive_scanner=archive_scanner,
                document_scanner=document_scanner,
                config=content_config
            )
            self.logger.info("FUSE manager initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize content scanner: {e}")
            self.content_scanner = None
            self.fuse_manager = None

    def _is_enforcement_bypassed(self, devnode: str) -> bool:
        """
        During encryption we temporarily allow writes; skip RO enforcement
        for the target device and any child/parent block nodes.
        """
        for bypass in self._bypass_enforcement:
            if devnode.startswith(bypass) or bypass.startswith(devnode):
                return True
        return False
    
    def _setup_fuse_overlay(self, device_path: str, base_mount: Optional[str] = None) -> None:
        """
        Set up FUSE overlay for content scanning on a mounted device.
        
        Args:
            device_path: Path to the device (e.g., /dev/mapper/usbenc-sdb1 or /dev/sdb1)
            base_mount: Optional pre-determined mount point. If None, will search for it.
        """
        if not self.fuse_manager:
            return
        
        try:
            # Wait for the device to be mounted (if mount point not provided)
            mount_point = base_mount
            
            if not mount_point:
                max_wait = 10
                start_time = time.time()
                
                while time.time() - start_time < max_wait:
                    result = subprocess.run(
                        ["findmnt", "-n", "-o", "TARGET", "-S", device_path],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        mount_point = result.stdout.strip()
                        break
                    time.sleep(0.5)
                
                if not mount_point:
                    self.logger.warning(f"Device {device_path} not mounted after {max_wait}s")
                    return
            
            # Skip if mount point is in hidden backing directory (already a FUSE backing mount)
            if '/.usb-enforcer-backing/' in mount_point or mount_point.endswith('.real'):
                self.logger.debug(f"Skipping FUSE overlay for backing mount: {mount_point}")
                return
            
            # Check if already mounted with FUSE overlay
            if mount_point in self.fuse_manager.mounts:
                self.logger.debug(f"FUSE overlay already active for {mount_point}")
                return
            
            self.logger.info(f"Setting up FUSE overlay for {mount_point}")
            
            # Define progress callback for notifications
            def progress_callback(filepath: str, progress: float, status: str, total_size: int, scanned_size: int):
                # Log progress
                self.logger.debug(
                    f"Scan progress: {filepath} - {progress:.1f}% - {status} - {scanned_size}/{total_size}"
                )
                
                # Emit event for GUI notifications (if DBus service is running)
                if self.dbus_service:
                    try:
                        self.dbus_service.emit_scan_progress(
                            filepath, progress, status, total_size, scanned_size
                        )
                    except Exception as e:
                        self.logger.debug(f"Failed to emit scan progress: {e}")
            
            # Define blocked file callback for notifications
            def blocked_callback(filepath: str, reason: str, patterns: str, match_count: int):
                # Log blocked file
                self.logger.warning(
                    f"File blocked: {filepath} - {reason} - Patterns: {patterns}"
                )
                
                # Emit notification (if DBus service is running)
                if self.dbus_service:
                    self.logger.info(f"Emitting ContentBlocked signal for {filepath}")
                    try:
                        self.dbus_service.emit_content_blocked(
                            filepath, reason, patterns, match_count
                        )
                        self.logger.info(f"ContentBlocked signal emitted successfully")
                    except Exception as e:
                        self.logger.error(f"Failed to emit blocked notification: {e}", exc_info=True)
                else:
                    self.logger.warning("DBus service not available, cannot emit ContentBlocked signal")
            
            # Add progress handler
            self.fuse_manager.add_progress_handler(progress_callback)
            
            # Add blocked file handler
            self.fuse_manager.add_blocked_handler(blocked_callback)
            
            # Need to unmount the device first, then remount through FUSE
            # For now, since FuseManager.mount() expects to mount the device itself,
            # we'll need to unmount, then let FUSE manager handle the remount
            try:
                subprocess.run(["umount", mount_point], check=False, capture_output=True)
                time.sleep(0.5)
            except Exception:
                pass
            
            # Create FUSE mount point with same path
            fuse_mount = mount_point
            
            # Determine if device is encrypted (mapper devices are LUKS encrypted)
            is_encrypted = '/mapper/' in device_path
            self.logger.debug(f"Device {device_path} - is_encrypted: {is_encrypted}")
            
            # Mount FUSE overlay (it will handle mounting the device internally)
            success = self.fuse_manager.mount(device_path, fuse_mount, is_encrypted=is_encrypted)
            
            if success:
                self.logger.info(f"FUSE overlay active for {fuse_mount}")
            else:
                self.logger.error(f"Failed to activate FUSE overlay for {fuse_mount}")
            
        except Exception as e:
            self.logger.error(f"Failed to set up FUSE overlay: {e}", exc_info=True)

    def handle_device(self, device_props: Dict[str, str], devnode: str, action: str) -> None:
        # Handle device removal - cleanup and remove from cache
        if action in ("remove", "unbind", "offline"):
            self.devices.pop(devnode, None)
            # Remove from bypass list if present
            self._bypass_enforcement.discard(devnode)
            # Try to clean up any stale mount points via udisks2
            self._cleanup_stale_mounts(devnode)
            return
        classification = classify.classify_device(device_props, devnode=devnode)
        self.devices[devnode] = {
            "devnode": devnode,
            "action": action,
            "classification": classification,
            "id_bus": device_props.get("ID_BUS", ""),
            "id_type": device_props.get("ID_TYPE", ""),
            "serial": device_props.get("ID_SERIAL_SHORT", device_props.get("ID_SERIAL", "")),
        }
        
        # Handle mapper devices (unlocked LUKS) - set up FUSE overlay if content scanning enabled
        if classification == constants.MAPPER and action in ("add", "change"):
            self.logger.info(f"DEBUG: Mapper device detected - classification={classification}, action={action}")
            self.logger.info(f"DEBUG: fuse_manager={self.fuse_manager is not None}, content_scanner={self.content_scanner is not None}")
            if self.fuse_manager and self.content_scanner:
                self.logger.info(f"Mapper device detected: {devnode}, setting up FUSE overlay")
                self._setup_fuse_overlay(devnode)
            else:
                self.logger.warning(f"Mapper device detected: {devnode}, no content scanning configured (fuse_manager={self.fuse_manager is not None}, content_scanner={self.content_scanner is not None})")
            return
        
        if self._is_enforcement_bypassed(devnode):
            log_fields = {
                constants.LOG_KEY_DEVNODE: devnode,
                constants.LOG_KEY_CLASSIFICATION: classification,
                constants.LOG_KEY_ACTION: "bypass",
                constants.LOG_KEY_RESULT: "allow",
                constants.LOG_KEY_POLICY_SOURCE: "daemon",
                constants.LOG_KEY_DEVTYPE: device_props.get("DEVTYPE", "unknown"),
                constants.LOG_KEY_BUS: device_props.get("ID_BUS", "unknown"),
                constants.LOG_KEY_SERIAL: device_props.get("ID_SERIAL_SHORT", device_props.get("ID_SERIAL", "")),
                constants.LOG_KEY_EVENT: constants.EVENT_ENFORCE,
            }
            self._log_event(f"bypassing enforcement for {devnode} (operation in progress)", log_fields)
            return
        log_fields = enforcer.enforce_policy(device_props, devnode, self.logger, self.config)
        log_fields[constants.LOG_KEY_EVENT] = constants.EVENT_ENFORCE
        self._log_event(f"handled {devnode} action={action} classification={classification}", log_fields)
        
        # Trigger automount for plaintext devices
        if log_fields.get(constants.LOG_KEY_ACTION) == "block_rw" and log_fields.get(constants.LOG_KEY_RESULT) == "allow":
            # Read-only mount (no exemption)
            self._trigger_mount_ro(devnode)
        elif log_fields.get(constants.LOG_KEY_ACTION) == "exempt" and log_fields.get(constants.LOG_KEY_RESULT) == "allow":
            # Writable mount (exempted user) - apply content scanning if enabled
            if self.fuse_manager and self.content_scanner:
                self._trigger_mount_rw_with_fuse(devnode)
            else:
                # No content scanning, just mount normally (will be writable)
                self._trigger_mount_rw(devnode)
    
    def _trigger_mount_rw(self, devnode: str) -> None:
        """
        Trigger a normal writable mount via udisks2 (for exempted plaintext devices without content scanning).
        """
        def do_mount():
            try:
                # Get the active session user
                uid = None
                gid = None
                username = None
                
                # Try to find logged-in user
                try:
                    result = subprocess.run(["who"], capture_output=True, text=True, check=False)
                    for line in result.stdout.splitlines():
                        parts = line.split()
                        if parts:
                            user = parts[0]
                            if user != "root":
                                try:
                                    pw = pwd.getpwnam(user)
                                    uid = pw.pw_uid
                                    gid = pw.pw_gid
                                    username = user
                                    break
                                except KeyError:
                                    continue
                except Exception:
                    pass
                
                # Wait briefly for udev to settle
                time.sleep(0.5)
                
                # Mount the device
                result = subprocess.run(
                    ["udisksctl", "mount", "-b", devnode, "--no-user-interaction"],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.returncode == 0:
                    self.logger.info(f"Auto-mounted writable (exempted, no scan): {devnode}")
                    
                    # Fix ownership if we found a user
                    if uid is not None and gid is not None and "at " in result.stdout:
                        mountpoint = result.stdout.split("at ")[-1].strip().rstrip(".")
                        try:
                            time.sleep(0.2)
                            os.chown(mountpoint, uid, gid)
                            self.logger.info(f"Fixed ownership of {mountpoint} to {username} ({uid}:{gid})")
                        except Exception as e:
                            self.logger.warning(f"Failed to fix ownership of {mountpoint}: {e}")
                else:
                    self.logger.debug(f"Mount via udisksctl failed for {devnode}: {result.stderr.strip()}")
            except Exception as e:
                self.logger.debug(f"Failed to trigger mount for {devnode}: {e}")
        
        # Run in background thread to avoid blocking udev processing
        threading.Thread(target=do_mount, daemon=True).start()

    def _trigger_mount_ro(self, devnode: str) -> None:
        """
        Trigger a read-only mount via udisks2 for plaintext devices.
        This is needed because our udev rules disable automounting for security.
        """
        def do_mount():
            try:
                # Get the active session user
                uid = None
                gid = None
                username = None
                
                # Try to find logged-in user
                try:
                    result = subprocess.run(["who"], capture_output=True, text=True, check=False)
                    for line in result.stdout.splitlines():
                        parts = line.split()
                        if parts:
                            user = parts[0]
                            if user != "root":
                                try:
                                    pw = pwd.getpwnam(user)
                                    uid = pw.pw_uid
                                    gid = pw.pw_gid
                                    username = user
                                    break
                                except KeyError:
                                    continue
                except Exception:
                    pass
                
                # Wait briefly for udev to settle
                time.sleep(0.5)
                
                # Use udisksctl to mount the device - it will respect the read-only block device setting
                result = subprocess.run(
                    ["udisksctl", "mount", "-b", devnode, "--no-user-interaction"],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.returncode == 0:
                    self.logger.info(f"Auto-mounted read-only: {devnode}")
                    
                    # Fix ownership if we found a user and the mount succeeded
                    if uid is not None and gid is not None and "at " in result.stdout:
                        mountpoint = result.stdout.split("at ")[-1].strip().rstrip(".")
                        try:
                            # Wait a moment for the mount to settle
                            time.sleep(0.2)
                            # Change ownership of the mountpoint
                            os.chown(mountpoint, uid, gid)
                            self.logger.info(f"Fixed ownership of {mountpoint} to {username} ({uid}:{gid})")
                        except Exception as e:
                            self.logger.warning(f"Failed to fix ownership of {mountpoint}: {e}")
                else:
                    # Device might already be mounted or mount might fail for other reasons
                    self.logger.debug(f"Mount via udisksctl failed for {devnode}: {result.stderr.strip()}")
            except Exception as e:
                self.logger.debug(f"Failed to trigger mount for {devnode}: {e}")
        
        # Run in background thread to avoid blocking udev processing
        threading.Thread(target=do_mount, daemon=True).start()
    
    def _trigger_mount_rw_with_fuse(self, devnode: str) -> None:
        """
        Trigger a writable mount via udisks2 for plaintext devices (when user is exempted),
        then overlay with FUSE for content scanning.
        """
        def do_mount():
            try:
                # Get the active session user
                uid = None
                gid = None
                username = None
                
                # Try to find logged-in user
                try:
                    result = subprocess.run(["who"], capture_output=True, text=True, check=False)
                    for line in result.stdout.splitlines():
                        parts = line.split()
                        if parts:
                            user = parts[0]
                            if user != "root":
                                try:
                                    pw = pwd.getpwnam(user)
                                    uid = pw.pw_uid
                                    gid = pw.pw_gid
                                    username = user
                                    break
                                except KeyError:
                                    continue
                except Exception:
                    pass
                
                # Wait briefly for udev to settle
                time.sleep(0.5)
                
                # Mount the device as writable
                result = subprocess.run(
                    ["udisksctl", "mount", "-b", devnode, "--no-user-interaction"],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.returncode == 0:
                    self.logger.info(f"Auto-mounted writable (exempted): {devnode}")
                    
                    # Extract mountpoint from output
                    if "at " in result.stdout:
                        mountpoint = result.stdout.split("at ")[-1].strip().rstrip(".")
                        
                        # Fix ownership if we found a user
                        if uid is not None and gid is not None:
                            try:
                                time.sleep(0.2)
                                os.chown(mountpoint, uid, gid)
                                self.logger.info(f"Fixed ownership of {mountpoint} to {username} ({uid}:{gid})")
                            except Exception as e:
                                self.logger.warning(f"Failed to fix ownership of {mountpoint}: {e}")
                        
                        # Set up FUSE overlay for content scanning
                        if self.fuse_manager and self.content_scanner:
                            self._setup_fuse_overlay(devnode, base_mount=mountpoint)
                else:
                    # Device might already be mounted
                    self.logger.debug(f"Mount via udisksctl failed for {devnode}: {result.stderr.strip()}")
            except Exception as e:
                self.logger.debug(f"Failed to trigger mount+FUSE for {devnode}: {e}")
        
        # Run in background thread to avoid blocking udev processing
        threading.Thread(target=do_mount, daemon=True).start()

    def list_devices(self) -> List[Dict[str, str]]:
        return list(self.devices.values())

    def get_device_status(self, devnode: str) -> Dict[str, str]:
        return self.devices.get(devnode, {})
    
    def get_scanner_statistics(self) -> Dict[str, str]:
        """Get content scanner statistics"""
        if not self.fuse_manager:
            return {}
        
        try:
            # Get aggregated statistics from all active mounts
            all_stats = {
                'files_scanned': 0,
                'files_blocked': 0,
                'files_allowed': 0,
                'total_bytes_scanned': 0,
                'patterns_detected': 0,
                'active_mounts': len(self.fuse_manager.mounts)
            }
            
            # Aggregate from all mounts
            for mount_point in self.fuse_manager.mounts:
                mount_stats = self.fuse_manager.get_statistics(mount_point)
                if mount_stats:
                    for key in ['files_scanned', 'files_blocked', 'files_allowed', 'total_bytes_scanned', 'patterns_detected']:
                        all_stats[key] += mount_stats.get(key, 0)
            
            # Convert all values to strings for DBus
            return {k: str(v) for k, v in all_stats.items()}
        except Exception as e:
            self.logger.error(f"Failed to get scanner statistics: {e}")
            return {}

    def _cleanup_stale_mounts(self, devnode: str) -> None:
        """
        Clean up stale mount points when a device is removed.
        This handles cases where devices are unplugged without proper unmounting.
        """
        try:
            # First, clean up any FUSE overlays that might be associated with this device
            if self.fuse_manager:
                # Check all FUSE mounts to see if any are backed by this device
                mounts_to_cleanup = []
                for mount_point in list(self.fuse_manager.mounts.keys()):
                    try:
                        _, _, real_mount = self.fuse_manager.mounts[mount_point]
                        # Check if the backing device is the one being removed
                        # Check both the hidden backing directory and direct mount
                        result = subprocess.run(
                            ["findmnt", "-n", "-o", "SOURCE", "-M", real_mount],
                            capture_output=True,
                            text=True,
                            check=False
                        )
                        if result.returncode == 0:
                            source = result.stdout.strip()
                            if devnode in source or source.startswith(devnode):
                                mounts_to_cleanup.append(mount_point)
                        else:
                            # Backing mount doesn't exist - orphaned FUSE
                            mounts_to_cleanup.append(mount_point)
                    except Exception as e:
                        self.logger.debug(f"Error checking FUSE mount {mount_point}: {e}")
                
                # Clean up identified FUSE mounts
                for mount_point in mounts_to_cleanup:
                    try:
                        self.logger.info(f"Cleaning up FUSE overlay: {mount_point}")
                        self.fuse_manager.unmount(mount_point)
                    except Exception as e:
                        self.logger.warning(f"Failed to cleanly unmount FUSE overlay {mount_point}: {e}")
            
            # Get list of mount points in /run/media
            result = subprocess.run(
                ["findmnt", "-n", "-o", "TARGET,SOURCE", "-t", "exfat,vfat,ext4,ext3,ext2"],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        mountpoint, source = parts[0], parts[1]
                        # Check if this mount point references the removed device
                        if devnode in source or source.startswith(devnode):
                            try:
                                subprocess.run(["umount", "-l", mountpoint], check=False)
                                # Try to remove the directory if it's in /run/media
                                if mountpoint.startswith("/run/media/"):
                                    subprocess.run(["rmdir", mountpoint], check=False)
                                self.logger.info(f"Cleaned up stale mount: {mountpoint}")
                            except Exception:
                                pass
        except Exception as e:
            self.logger.debug(f"Mount cleanup check failed: {e}")

    def _mapper_name_for(self, devnode: str) -> str:
        basename = devnode.split("/")[-1]
        return f"usbenc-{basename}"

    def request_unlock(self, devnode: str, mapper_name: Optional[str], passphrase: str) -> str:
        self.logger.info(f"request_unlock called for {devnode}")
        token = passphrase  # now treated as token from secret socket
        passphrase = self._consume_secret(token, "unlock")
        self._assert_usb_storage(devnode)
        mapper = mapper_name or self._mapper_name_for(devnode)
        self._log_event("unlock_start", {constants.LOG_KEY_EVENT: constants.EVENT_UNLOCK, constants.LOG_KEY_DEVNODE: devnode, constants.LOG_KEY_ACTION: "unlock_start"})
        
        # Get user info for ownership fixing
        uid = None
        gid = None
        sudo_user = os.environ.get("SUDO_USER")
        if sudo_user:
            try:
                pw = pwd.getpwnam(sudo_user)
                uid = pw.pw_uid
                gid = pw.pw_gid
            except KeyError:
                pass
        
        if uid is None:
            pkexec_uid = os.environ.get("PKEXEC_UID")
            if pkexec_uid:
                try:
                    uid = int(pkexec_uid)
                    pw = pwd.getpwuid(uid)
                    gid = pw.pw_gid
                except (ValueError, KeyError):
                    pass
        
        try:
            mapper_path = crypto_engine.unlock_luks(devnode, mapper, passphrase)
            
            # If content scanning is enabled, wait for mount and overlay with FUSE
            self.logger.debug(f"After unlock: fuse_manager={self.fuse_manager is not None}, content_scanner={self.content_scanner is not None}")
            if self.fuse_manager and self.content_scanner:
                self.logger.info(f"Setting up FUSE overlay for {mapper_path}")
                self._setup_fuse_overlay(mapper_path)
            else:
                self.logger.warning(f"Skipping FUSE overlay - fuse_manager={self.fuse_manager is not None}, content_scanner={self.content_scanner is not None}")
            
            # Encrypted devices are auto-mounted by the system (UDISKS_AUTO=1 in udev rules)
            # The desktop environment handles ownership automatically
            self._log_event(
                "unlock_done",
                {
                    constants.LOG_KEY_EVENT: constants.EVENT_UNLOCK,
                    constants.LOG_KEY_DEVNODE: devnode,
                    constants.LOG_KEY_ACTION: "unlock_done",
                    constants.LOG_KEY_RESULT: "allow",
                },
            )
            return mapper_path
        except Exception as exc:
            self._log_event(
                "unlock_fail",
                {
                    constants.LOG_KEY_EVENT: constants.EVENT_UNLOCK,
                    constants.LOG_KEY_DEVNODE: devnode,
                    constants.LOG_KEY_ACTION: "unlock_fail",
                    constants.LOG_KEY_RESULT: "fail",
                },
            )
            raise

    def request_encrypt(self, devnode: str, mapper_name: Optional[str], passphrase: str, fs_type: str, label: Optional[str]) -> str:
        token = passphrase  # now treated as token from secret socket
        passphrase = self._consume_secret(token, "encrypt")
        self._assert_usb_storage(devnode)
        mapper = mapper_name or self._mapper_name_for(devnode)
        if len(passphrase) < self.config.min_passphrase_length:
            raise ValueError(f"Passphrase too short (min {self.config.min_passphrase_length})")
        self._log_event("encrypt_start", {constants.LOG_KEY_EVENT: constants.EVENT_ENCRYPT, constants.LOG_KEY_DEVNODE: devnode, constants.LOG_KEY_ACTION: "encrypt_start"})

        def progress(stage: str, pct: int):
            self._log_event(
                f"encrypt_progress:{stage}",
                {
                    constants.LOG_KEY_EVENT: constants.EVENT_ENCRYPT,
                    constants.LOG_KEY_DEVNODE: devnode,
                    constants.LOG_KEY_ACTION: f"encrypt_{stage}",
                    "PROGRESS": str(pct),
                },
            )

        # Get the real user who invoked this (when called via sudo or from user session)
        uid = None
        gid = None
        username = None
        sudo_user = os.environ.get("SUDO_USER")
        if sudo_user:
            try:
                pw = pwd.getpwnam(sudo_user)
                uid = pw.pw_uid
                gid = pw.pw_gid
                username = sudo_user
            except KeyError:
                pass
        
        # Fallback: get from PKEXEC_UID or try to find a logged-in user
        if uid is None:
            pkexec_uid = os.environ.get("PKEXEC_UID")
            if pkexec_uid:
                try:
                    uid = int(pkexec_uid)
                    pw = pwd.getpwuid(uid)
                    gid = pw.pw_gid
                    username = pw.pw_name
                except (ValueError, KeyError):
                    pass
        
        # Last resort: get first non-root user with active session
        if uid is None:
            try:
                import subprocess
                result = subprocess.run(["who"], capture_output=True, text=True, check=False)
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if parts:
                        user = parts[0]
                        if user != "root":
                            try:
                                pw = pwd.getpwnam(user)
                                uid = pw.pw_uid
                                gid = pw.pw_gid
                                username = user
                                break
                            except KeyError:
                                continue
            except Exception:
                pass

        self._bypass_enforcement.add(devnode)
        try:
            mountpoint = crypto_engine.encrypt_device(
                devnode,
                mapper,
                passphrase,
                fs_type or self.config.filesystem_type,
                self.config.default_encrypted_mount_opts,
                label,
                progress_cb=progress,
                kdf_opts=self.config.kdf,
                cipher_opts=self.config.cipher,
                uid=uid,
                gid=gid,
                username=username,
            )
            self._log_event(
                "encrypt_done",
                {
                    constants.LOG_KEY_EVENT: constants.EVENT_ENCRYPT,
                    constants.LOG_KEY_DEVNODE: devnode,
                    constants.LOG_KEY_ACTION: "encrypt_done",
                    constants.LOG_KEY_RESULT: "allow",
                },
            )
            return mountpoint
        except Exception as exc:
            self._log_event(
                "encrypt_fail",
                {
                    constants.LOG_KEY_EVENT: constants.EVENT_ENCRYPT,
                    constants.LOG_KEY_DEVNODE: devnode,
                    constants.LOG_KEY_ACTION: "encrypt_fail",
                    constants.LOG_KEY_RESULT: "fail",
                },
            )
            raise
        finally:
            self._bypass_enforcement.discard(devnode)

    def run(self) -> None:
        self.logger.info("USB encryption enforcer daemon starting")

        def stop(*_args):
            self.logger.info("Stopping daemon")
            self._stop_event.set()

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)

        # Start DBus service
        dbus_service = dbus_api.UsbEnforcerDBus(
            self.logger,
            self.list_devices,
            self.get_device_status,
            self.request_unlock,
            self.request_encrypt,
            self.get_scanner_statistics,
        )
        dbus_service.Export()
        self.dbus_service = dbus_service

        if GLib:
            def _run_loop():
                loop = GLib.MainLoop()
                self._dbus_loop = loop
                loop.run()

            threading.Thread(target=_run_loop, daemon=True).start()

        self._start_secret_socket()
        monitor_thread = threading.Thread(target=udev_monitor.start_monitor, args=(self.handle_device, self.logger), daemon=True)
        monitor_thread.start()

        while not self._stop_event.is_set():
            self._stop_event.wait(0.5)
        self.logger.info("USB encryption enforcer daemon stopped")
        self._cleanup_secret_socket()

    def _assert_usb_storage(self, devnode: str) -> None:
        """
        Ensure requests only target USB block storage (disk/partition).
        """
        self.logger.info(f"_assert_usb_storage called with devnode: '{devnode}'")
        self.logger.info(f"  Available devices in cache: {list(self.devices.keys())}")
        props = self.devices.get(devnode, {})
        self.logger.info(f"  Props from cache: {bool(props)} (has {len(props)} keys)")
        if not props:
            self.logger.info(f"  Device not in cache, querying pyudev...")
            try:
                dev = pyudev.Devices.from_device_file(self._udev_context, devnode)
                props = dict(dev)
                self.logger.info(f"  Props from pyudev: ID_BUS={props.get('ID_BUS')}, count={len(props)}")
            except Exception as e:
                self.logger.warning(f"Failed to get udev properties for {devnode}: {e}")
                raise ValueError(f"Could not determine device properties for {devnode}")
        
        # Check USB bus
        # Cache uses lowercase keys, pyudev uses uppercase
        id_bus = props.get("ID_BUS") or props.get("id_bus")
        if id_bus != "usb":
            raise ValueError(f"{devnode} is not a USB device (ID_BUS={id_bus})")
        
        # Check device type - accept disk, partition, or if DEVTYPE is disk
        id_type = props.get("ID_TYPE") or props.get("id_type")
        devtype = props.get("DEVTYPE") or props.get("devtype")
        
        if id_type not in ("disk", "partition") and devtype != "disk":
            raise ValueError(f"{devnode} is not a block storage device (ID_TYPE={id_type}, DEVTYPE={devtype})")

    def _start_secret_socket(self) -> None:
        """
        UNIX socket that receives passphrases and returns a one-time token.
        Clients then pass the token over DBus; passphrases never traverse DBus.
        """
        try:
            if os.path.exists(self._secret_socket_path):
                os.unlink(self._secret_socket_path)
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(self._secret_socket_path)
            # Default: allow users in the group (plugdev) to connect; fall back to 0666 so user-session UI can reach it
            socket_mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP
            target_gid = None
            try:
                target_gid = grp.getgrnam(os.environ.get("USB_EE_SOCKET_GROUP", "plugdev")).gr_gid
            except KeyError:
                target_gid = None
            except Exception:
                target_gid = None
            if target_gid is not None:
                try:
                    os.chown(self._secret_socket_path, 0, target_gid)
                except PermissionError:
                    target_gid = None
            if target_gid is None:
                socket_mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH
            os.chmod(self._secret_socket_path, socket_mode)
            sock.listen(5)
            self._secret_socket = sock
            threading.Thread(target=self._secret_socket_loop, daemon=True).start()
            self.logger.info("Secret socket listening at %s", self._secret_socket_path)
        except Exception as exc:
            self.logger.error("Failed to start secret socket: %s", exc)
            self._secret_socket = None

    def _secret_socket_loop(self) -> None:
        if not self._secret_socket:
            return
        while not self._stop_event.is_set():
            try:
                conn, _addr = self._secret_socket.accept()
            except OSError as exc:
                if exc.errno == errno.EBADF:
                    break
                continue
            threading.Thread(target=self._handle_secret_client, args=(conn,), daemon=True).start()

    def _handle_secret_client(self, conn: socket.socket) -> None:
        try:
            data = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                if len(data) > 8192:
                    break
            try:
                payload = json.loads(data.decode("utf-8"))
            except Exception:
                self._send_secret_response(conn, error="invalid JSON")
                return
            op = payload.get("op")
            passphrase = payload.get("passphrase")
            devnode = payload.get("devnode")
            mapper_name = payload.get("mapper")
            if op not in ("encrypt", "unlock") or not passphrase or not devnode:
                self._send_secret_response(conn, error="missing op/devnode/passphrase")
                return
            token = payload.get("token") or secrets.token_hex(16)
            self._store_secret(token, op, passphrase)
            self._send_secret_response(conn, token=token, mapper=mapper_name, devnode=devnode)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _store_secret(self, token: str, op: str, passphrase: str) -> None:
        with self._secret_lock:
            self._secret_store[token] = (op, passphrase)

    def _consume_secret(self, token: str, op: str) -> str:
        with self._secret_lock:
            entry = self._secret_store.pop(token, None)
        if not entry:
            raise ValueError("Invalid or expired token")
        stored_op, passphrase = entry
        if stored_op != op:
            raise ValueError("Token operation mismatch")
        return passphrase

    def _send_secret_response(self, conn: socket.socket, token: Optional[str] = None, mapper: Optional[str] = None, devnode: Optional[str] = None, error: Optional[str] = None) -> None:
        resp = {"status": "ok" if not error else "error"}
        if token:
            resp["token"] = token
        if mapper:
            resp["mapper"] = mapper
        if devnode:
            resp["devnode"] = devnode
        if error:
            resp["error"] = error
        try:
            conn.sendall(json.dumps(resp).encode("utf-8"))
        except Exception:
            pass

    def _cleanup_secret_socket(self) -> None:
        try:
            if self._secret_socket:
                try:
                    self._secret_socket.close()
                except Exception:
                    pass
            if os.path.exists(self._secret_socket_path):
                os.unlink(self._secret_socket_path)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="USB encryption enforcement daemon (DLP).")
    parser.add_argument("--config", type=str, help="Path to config.toml")
    args = parser.parse_args()
    daemon = Daemon(config_path=args.config)
    daemon.run()


if __name__ == "__main__":
    main()

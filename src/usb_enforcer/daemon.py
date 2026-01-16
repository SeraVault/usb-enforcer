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
import struct
import subprocess
import threading
import time
import shutil
from typing import Dict, List, Optional, Set, Tuple

import pyudev

from . import config as config_module, constants, dbus_api, logging_utils
from .encryption import classify, crypto_engine, enforcer, udev_monitor, user_utils

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
        self._secret_store: Dict[str, Tuple[str, str, float]] = {}  # token -> (op, passphrase, ts)
        self._secret_lock = threading.Lock()
        self._secret_ttl_seconds = self.config.secret_token_ttl_seconds
        self._secret_max_tokens = self.config.secret_token_max
        self._fuse_handlers_registered = False
        
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

            self._cleanup_existing_mounts(mount_point, device_path=device_path)
            
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
            
            if not self._fuse_handlers_registered:
                # Add handlers once to avoid duplicates on repeated mounts.
                self.fuse_manager.add_progress_handler(progress_callback)
                self.fuse_manager.add_blocked_handler(blocked_callback)
                self._fuse_handlers_registered = True
            
            # Move the existing mount to a hidden backing directory to preserve ownership/options.
            parent_dir = os.path.dirname(mount_point)
            drive_name = os.path.basename(mount_point)
            hidden_base = os.path.join(parent_dir, ".usb-enforcer-backing")
            real_mount = os.path.join(hidden_base, drive_name)
            try:
                os.makedirs(hidden_base, exist_ok=True)
                os.makedirs(real_mount, exist_ok=True)
                def _move_mount() -> subprocess.CompletedProcess:
                    return subprocess.run(
                        ["mount", "--move", mount_point, real_mount],
                        check=False,
                        capture_output=True,
                        text=True,
                    )

                def _make_private(path: str) -> None:
                    subprocess.run(
                        ["mount", "--make-rprivate", path],
                        check=False,
                        capture_output=True,
                        text=True,
                    )

                # /run/media is commonly a shared mount; ensure this subtree is private.
                _make_private(mount_point)
                _make_private(parent_dir)
                parent_parent = os.path.dirname(parent_dir)
                if parent_parent:
                    _make_private(parent_parent)
                    # /run is typically the propagation root for /run/media.
                    _make_private(os.path.dirname(parent_parent))

                move_result = _move_mount()
                if move_result.returncode != 0 and "shared mount" in move_result.stderr:
                    # Retry after forcing the subtree to private.
                    _make_private(mount_point)
                    _make_private(parent_dir)
                    if parent_parent:
                        _make_private(parent_parent)
                        _make_private(os.path.dirname(parent_parent))
                    move_result = _move_mount()
                if move_result.returncode != 0:
                    self.logger.error(
                        f"Failed to move mount for {mount_point}: {move_result.stderr.strip()}"
                    )
                    return
            except Exception as e:
                self.logger.error(f"Failed to move mount for {mount_point}: {e}")
                return
            
            # Create FUSE mount point with same path
            fuse_mount = mount_point
            
            # Determine if device is encrypted (mapper devices are LUKS encrypted)
            is_encrypted = '/mapper/' in device_path
            self.logger.debug(f"Device {device_path} - is_encrypted: {is_encrypted}")
            
            # Mount FUSE overlay on top of the moved mount to preserve ownership/options
            success = self.fuse_manager.mount(
                real_mount,
                fuse_mount,
                is_encrypted=is_encrypted,
                source_is_mount=True,
            )
            
            if success:
                self.logger.info(f"FUSE overlay active for {fuse_mount}")
            else:
                self.logger.error(f"Failed to activate FUSE overlay for {fuse_mount}")
                try:
                    subprocess.run(
                        ["mount", "--move", real_mount, mount_point],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                except Exception:
                    pass
            
        except Exception as e:
            self.logger.error(f"Failed to set up FUSE overlay: {e}", exc_info=True)

    def _cleanup_existing_mounts(self, mount_point: str, device_path: Optional[str] = None) -> None:
        """
        Clean up any existing FUSE/backing mounts for this mount point.
        """
        try:
            fuse_check = subprocess.run(
                ["findmnt", "-rn", "-o", "FSTYPE", "-M", mount_point],
                capture_output=True,
                text=True,
                check=False
            )
            if fuse_check.returncode == 0 and "fuse" in fuse_check.stdout.strip():
                fusermount_cmd = shutil.which("fusermount3") or shutil.which("fusermount") or "fusermount"
                subprocess.run([fusermount_cmd, "-u", mount_point], check=False)
        except Exception:
            pass

        try:
            parent_dir = os.path.dirname(mount_point)
            drive_name = os.path.basename(mount_point)
            hidden_base = os.path.join(parent_dir, ".usb-enforcer-backing")
            real_mount = os.path.join(hidden_base, drive_name)
            real_check = subprocess.run(
                ["findmnt", "-rn", "-o", "SOURCE", "-M", real_mount],
                capture_output=True,
                text=True,
                check=False
            )
            if real_check.returncode == 0 and real_check.stdout.strip():
                source = real_check.stdout.strip()
                if not device_path or source.startswith(device_path) or device_path in source:
                    subprocess.run(["umount", "-l", real_mount], check=False)
            if os.path.isdir(real_mount):
                try:
                    os.rmdir(real_mount)
                except OSError:
                    pass
            if os.path.isdir(hidden_base):
                try:
                    os.rmdir(hidden_base)
                except OSError:
                    pass
        except Exception:
            pass

    def _plaintext_mount_options(self, readonly: bool) -> List[str]:
        """
        Build mount options for plaintext devices based on config.
        """
        opts = list(self.config.default_plain_mount_opts or [])
        if readonly:
            if "ro" not in opts:
                opts.append("ro")
            if "rw" in opts:
                opts.remove("rw")
        else:
            if "rw" not in opts:
                opts.append("rw")
            if "ro" in opts:
                opts.remove("ro")
        if self.config.require_noexec_on_plain:
            if "noexec" not in opts:
                opts.append("noexec")
        else:
            if "noexec" in opts:
                opts.remove("noexec")
        return opts

    def _mount_opts_str(self, opts: List[str]) -> str:
        return ",".join(opts)

    def _get_active_session_user(self) -> Tuple[Optional[int], Optional[int], Optional[str]]:
        """
        Resolve the active local session user for mounting decisions.
        """
        username = user_utils.get_active_session_user()
        if not username:
            return None, None, None
        try:
            pw = pwd.getpwnam(username)
            return pw.pw_uid, pw.pw_gid, username
        except KeyError:
            return None, None, None

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
        policy_action = log_fields.get(constants.LOG_KEY_ACTION)
        policy_result = log_fields.get(constants.LOG_KEY_RESULT)
        self.logger.info(f"Policy decision for {devnode}: action={policy_action}, result={policy_result}")
        
        if policy_action == "block_rw" and policy_result == "allow":
            # Plaintext device - check if write is allowed with content scanning
            if self.config.allow_plaintext_write_with_scanning and self.fuse_manager and self.content_scanner:
                # Allow write with FUSE overlay for content scanning
                self.logger.info(f"Triggering writable mount with content scanning for {devnode}")
                self._trigger_mount_rw_with_fuse(devnode)
            else:
                # Read-only mount (no exemption, or no scanning available)
                self.logger.info(f"Triggering read-only mount for {devnode}")
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
                # Get the active local session user
                uid, gid, username = self._get_active_session_user()
                
                # Wait briefly for udev to settle
                time.sleep(0.5)
                mount_opts = self._plaintext_mount_options(readonly=False)
                mount_opts_str = self._mount_opts_str(mount_opts)
                
                # Mount the device
                result = subprocess.run(
                    ["udisksctl", "mount", "-b", devnode, "-o", mount_opts_str, "--no-user-interaction"],
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
                # Get the active local session user
                uid, gid, username = self._get_active_session_user()
                
                # Wait briefly for udev to settle
                time.sleep(0.5)
                mount_opts = self._plaintext_mount_options(readonly=True)
                mount_opts_str = self._mount_opts_str(mount_opts)
                
                # For plaintext devices, mount directly to /media/<username>/ so user can access it
                # (udisks would mount under /run/media/root/ which user can't access)
                if uid is not None and username:
                    # Get drive label
                    label_result = subprocess.run(
                        ["blkid", "-s", "LABEL", "-o", "value", devnode],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    label = label_result.stdout.strip() if label_result.returncode == 0 and label_result.stdout.strip() else os.path.basename(devnode)
                    
                    # Mount to /media/<username>/<label>
                    mount_point = f"/media/{username}/{label}"
                    try:
                        os.makedirs(mount_point, mode=0o755, exist_ok=True)
                        os.chown(mount_point, uid, -1)
                    except Exception as e:
                        self.logger.error(f"Failed to create mount point {mount_point}: {e}")
                        return
                    
                    # Mount read-only
                    result = subprocess.run(
                        [
                            "mount",
                            "-o",
                            "{},uid={},gid={}".format(mount_opts_str, uid, gid),
                            devnode,
                            mount_point,
                        ],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    if result.returncode == 0:
                        self.logger.info(f"Auto-mounted read-only: {devnode} at {mount_point}")
                    else:
                        self.logger.warning(f"Mount failed for {devnode}: {result.stderr.strip()}")
                        try:
                            os.rmdir(mount_point)
                        except:
                            pass
                else:
                    # No user found, use udisksctl as fallback
                    result = subprocess.run(
                        ["udisksctl", "mount", "-b", devnode, "-o", mount_opts_str, "--no-user-interaction"],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    if result.returncode == 0:
                        self.logger.info(f"Auto-mounted read-only: {devnode}")
                        if "at " in result.stdout:
                            mountpoint = result.stdout.split("at ")[-1].strip().rstrip(".")
                            self.logger.info(f"Mounted at: {mountpoint}")
                    else:
                        self.logger.warning(f"Mount via udisksctl failed for {devnode}: {result.stderr.strip()}")
                return
            except Exception as e:
                self.logger.debug(f"Failed to trigger read-only mount for {devnode}: {e}")
        
        # Run in background thread to avoid blocking udev processing
        threading.Thread(target=do_mount, daemon=True).start()
    
    def _trigger_mount_rw_with_fuse(self, devnode: str) -> None:
        """
        Trigger a writable mount via udisks2 for plaintext devices (when user is exempted),
        then overlay with FUSE for content scanning.
        """
        def do_mount():
            try:
                # Get the active local session user
                uid, gid, username = self._get_active_session_user()
                
                # Wait briefly for udev to settle
                time.sleep(0.5)
                mount_opts = self._plaintext_mount_options(readonly=False)
                mount_opts_str = self._mount_opts_str(mount_opts)
                
                # Mount the device as writable
                result = subprocess.run(
                    ["udisksctl", "mount", "-b", devnode, "-o", mount_opts_str, "--no-user-interaction"],
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
            self._cleanup_orphaned_fuse_mounts(devnode=devnode)
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

    def _cleanup_orphaned_fuse_mounts(self, devnode: Optional[str] = None) -> None:
        """
        Clean up FUSE/backing mounts even if the daemon has restarted.
        """
        try:
            result = subprocess.run(
                ["findmnt", "-rn", "-o", "TARGET,SOURCE,FSTYPE"],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode != 0:
                return
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) < 3:
                    continue
                target, source, fstype = parts[0], parts[1], parts[2]
                if "/.usb-enforcer-backing/" not in target:
                    continue
                if devnode and devnode not in source and not source.startswith(devnode):
                    continue
                hidden_base = os.path.dirname(target)
                parent_dir = os.path.dirname(hidden_base)
                drive_name = os.path.basename(target)
                fuse_mount = os.path.join(parent_dir, drive_name)
                # Try to unmount FUSE mount if present.
                try:
                    fuse_check = subprocess.run(
                        ["findmnt", "-rn", "-o", "FSTYPE", "-M", fuse_mount],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    if fuse_check.returncode == 0 and "fuse" in fuse_check.stdout.strip():
                        fusermount_cmd = shutil.which("fusermount3") or shutil.which("fusermount") or "fusermount"
                        subprocess.run([fusermount_cmd, "-u", fuse_mount], check=False)
                except Exception:
                    pass
                # Unmount backing mount and cleanup.
                subprocess.run(["umount", "-l", target], check=False)
                try:
                    if os.path.isdir(target):
                        os.rmdir(target)
                except Exception:
                    pass
                try:
                    if os.path.isdir(hidden_base):
                        os.rmdir(hidden_base)
                except Exception:
                    pass
        except Exception as e:
            self.logger.debug(f"Orphaned FUSE cleanup failed: {e}")

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
        self._cleanup_orphaned_fuse_mounts()
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
            # Default: allow users in the group (plugdev) to connect.
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
            if not self._secret_client_allowed(conn):
                self._send_secret_response(conn, error="unauthorized")
                return
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

    def _secret_client_allowed(self, conn: socket.socket) -> bool:
        """
        Only allow active local desktop session users to access the secret socket.
        """
        try:
            ucred = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            _pid, uid, _gid = struct.unpack("3i", ucred)
        except Exception:
            return False

        if uid == 0:
            return True

        active_users = user_utils.get_active_users()
        try:
            username = pwd.getpwuid(uid).pw_name
        except KeyError:
            return False
        return username in active_users

    def _store_secret(self, token: str, op: str, passphrase: str) -> None:
        with self._secret_lock:
            now = time.time()
            expired = [t for t, (_, _, ts) in self._secret_store.items() if now - ts > self._secret_ttl_seconds]
            for t in expired:
                self._secret_store.pop(t, None)
            if len(self._secret_store) >= self._secret_max_tokens:
                oldest_token = min(self._secret_store.items(), key=lambda item: item[1][2])[0]
                self._secret_store.pop(oldest_token, None)
            self._secret_store[token] = (op, passphrase, now)

    def _consume_secret(self, token: str, op: str) -> str:
        with self._secret_lock:
            entry = self._secret_store.pop(token, None)
        if not entry:
            raise ValueError("Invalid or expired token")
        stored_op, passphrase, ts = entry
        if time.time() - ts > self._secret_ttl_seconds:
            raise ValueError("Invalid or expired token")
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

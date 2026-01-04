from __future__ import annotations

import argparse
import logging
import os
import pwd
import signal
import subprocess
import threading
import time
from typing import Dict, List, Optional, Set

from . import classify, config as config_module, constants, crypto_engine, dbus_api, enforcer, logging_utils, udev_monitor

try:
    from gi.repository import GLib  # type: ignore
except Exception:  # pragma: no cover
    GLib = None


class Daemon:
    def __init__(self, config_path=None):
        self.config = config_module.Config.load(config_path)
        self.logger = logging_utils.setup_logging()
        self.devices: Dict[str, Dict[str, str]] = {}
        self._stop_event = threading.Event()
        self.dbus_service = None
        self._dbus_loop = None
        self._bypass_enforcement: Set[str] = set()

    def _emit_event(self, fields: Dict[str, str]) -> None:
        if self.dbus_service:
            self.dbus_service.emit_event(fields)

    def _log_event(self, message: str, fields: Dict[str, str]) -> None:
        logging_utils.log_structured(self.logger, message, fields)
        self._emit_event(fields)

    def _is_enforcement_bypassed(self, devnode: str) -> bool:
        """
        During encryption we temporarily allow writes; skip RO enforcement
        for the target device and any child/parent block nodes.
        """
        for bypass in self._bypass_enforcement:
            if devnode.startswith(bypass) or bypass.startswith(devnode):
                return True
        return False

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

    def list_devices(self) -> List[Dict[str, str]]:
        return list(self.devices.values())

    def get_device_status(self, devnode: str) -> Dict[str, str]:
        return self.devices.get(devnode, {})

    def _mapper_name_for(self, devnode: str) -> str:
        basename = devnode.split("/")[-1]
        return f"usbenc-{basename}"

    def _cleanup_stale_mounts(self, devnode: str) -> None:
        """
        Clean up stale mount points when a device is removed.
        This handles cases where devices are unplugged without proper unmounting.
        """
        try:
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

    def _fix_ownership_after_mount(self, mapper_path: str, uid: int, gid: int, max_wait: int = 10) -> None:
        """
        Wait for udisks2 to automount the mapper device, then fix ownership.
        This runs in a background thread to avoid blocking the unlock operation.
        """
        def fix_ownership():
            # Wait for the device to be mounted (check every 0.5s for up to max_wait seconds)
            mountpoint = None
            for _ in range(max_wait * 2):
                try:
                    result = subprocess.run(
                        ["findmnt", "-n", "-o", "TARGET", mapper_path],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        mountpoint = result.stdout.strip()
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            
            if mountpoint:
                try:
                    # Fix ownership of mountpoint and top-level contents
                    os.chown(mountpoint, uid, gid)
                    for root, dirs, files in os.walk(mountpoint):
                        os.chown(root, uid, gid)
                        for d in dirs:
                            os.chown(os.path.join(root, d), uid, gid)
                        break  # Only process top level
                    self.logger.info(f"Fixed ownership of {mountpoint} to {uid}:{gid}")
                except Exception as e:
                    self.logger.warning(f"Failed to fix ownership of {mountpoint}: {e}")
        
        threading.Thread(target=fix_ownership, daemon=True).start()

    def request_unlock(self, devnode: str, mapper_name: Optional[str], passphrase: str) -> str:
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
            
            # Schedule ownership fix after automount
            if uid is not None and gid is not None:
                self._fix_ownership_after_mount(mapper_path, uid, gid)
            
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
        dbus_service = dbus_api.UsbEncryptionEnforcerDBus(
            self.logger,
            self.list_devices,
            self.get_device_status,
            self.request_unlock,
            self.request_encrypt,
        )
        dbus_service.Export()
        self.dbus_service = dbus_service

        if GLib:
            def _run_loop():
                loop = GLib.MainLoop()
                self._dbus_loop = loop
                loop.run()

            threading.Thread(target=_run_loop, daemon=True).start()

        monitor_thread = threading.Thread(target=udev_monitor.start_monitor, args=(self.handle_device, self.logger), daemon=True)
        monitor_thread.start()

        while not self._stop_event.is_set():
            self._stop_event.wait(0.5)
        self.logger.info("USB encryption enforcer daemon stopped")


def main():
    parser = argparse.ArgumentParser(description="USB encryption enforcement daemon (DLP).")
    parser.add_argument("--config", type=str, help="Path to config.toml")
    args = parser.parse_args()
    daemon = Daemon(config_path=args.config)
    daemon.run()


if __name__ == "__main__":
    main()

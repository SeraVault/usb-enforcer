from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Dict, Optional

from .. import constants
from . import classify, user_utils


def set_block_read_only(devnode: str, logger: logging.Logger) -> bool:
    """
    Force block device read-only using sysfs knob.
    Returns True on success or if already RO.
    """
    block_name = Path(devnode).name
    # /sys/class/block/<name>/ro exists for both disks and partitions
    ro_path = Path("/sys/class/block") / block_name / "ro"
    if not ro_path.exists():
        logger.debug("ro sysfs path missing for %s", devnode)
        return False
    try:
        current = ro_path.read_text().strip()
        if current == "1":
            return True
        ro_path.write_text("1")
        return True
    except PermissionError:
        logger.warning("Permission denied setting RO via sysfs for %s; trying blockdev", devnode)
    except OSError as exc:  # pragma: no cover
        logger.error("Failed to set RO via sysfs for %s: %s", devnode, exc)

    # Fallback to blockdev ioctl
    try:
        subprocess.run(["blockdev", "--setro", devnode], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as exc:
        logger.error("blockdev --setro failed for %s: %s", devnode, exc.stderr.decode().strip())
        return False


def enforce_policy(device_props: Dict[str, str], devnode: str, logger: logging.Logger, config) -> Dict[str, str]:
    """
    Apply block-level RO for plaintext USB partitions with filesystems.
    Whole disks are left writable to allow partitioning operations.
    Users in exempted groups bypass all enforcement.
    """
    classification = classify.classify_device(device_props, devnode=devnode)
    result = {
        constants.LOG_KEY_DEVNODE: devnode,
        constants.LOG_KEY_CLASSIFICATION: classification,
        constants.LOG_KEY_ACTION: "noop",
        constants.LOG_KEY_RESULT: "allow",
        constants.LOG_KEY_POLICY_SOURCE: "daemon",
        constants.LOG_KEY_DEVTYPE: device_props.get("DEVTYPE", "unknown"),
        constants.LOG_KEY_BUS: device_props.get("ID_BUS", "unknown"),
        constants.LOG_KEY_SERIAL: device_props.get("ID_SERIAL_SHORT", device_props.get("ID_SERIAL", "")),
    }

    # Check if any active user is in an exempted group
    is_exempted, exemption_reason = user_utils.any_active_user_in_groups(config.exempted_groups, logger)
    if is_exempted:
        result[constants.LOG_KEY_ACTION] = "exempt"
        result[constants.LOG_KEY_RESULT] = "allow"
        result["exemption_reason"] = exemption_reason
        logger.info(f"Exempting {devnode}: {exemption_reason}")
        return result

    # Apply block-level RO to partitions with filesystems OR whole disks with filesystems
    # Leave unformatted whole disks writable to allow partitioning
    devtype = device_props.get("DEVTYPE", "")
    fs_usage = device_props.get("ID_FS_USAGE", "")
    fs_type = device_props.get("ID_FS_TYPE", "")
    has_filesystem = fs_type != "" and (fs_usage == "filesystem" or fs_usage == "")
    
    logger.debug(f"enforce_policy: {devnode} devtype={devtype} fs_usage={fs_usage} fs_type={fs_type} has_filesystem={has_filesystem}")
    
    content_scanning = getattr(config, "content_scanning", None)
    content_scanning_enabled = bool(content_scanning and getattr(content_scanning, "enabled", False))
    allow_plaintext_with_scanning = (
        config.allow_plaintext_write_with_scanning and content_scanning_enabled
    )

    # Apply RO to: partitions with filesystems, OR whole disks with filesystems (but not unformatted disks)
    # Skip RO when plaintext writes are allowed with content scanning.
    should_enforce_ro = (
        classification == constants.PLAINTEXT
        and has_filesystem
        and (devtype == "partition" or (devtype == "disk" and has_filesystem))
        and not allow_plaintext_with_scanning
    )
    
    if should_enforce_ro:
        result[constants.LOG_KEY_ACTION] = "block_rw"
        ok = set_block_read_only(devnode, logger)
        result[constants.LOG_KEY_RESULT] = "allow" if ok else "fail"
    elif classification == constants.LUKS1 and not config.allow_luks1_readonly:
        result[constants.LOG_KEY_ACTION] = "block_mount"
        result[constants.LOG_KEY_RESULT] = "deny"
    elif classification in (constants.LUKS2_LOCKED, constants.LUKS2_UNLOCKED, constants.MAPPER):
        result[constants.LOG_KEY_ACTION] = "allow_rw"
    else:
        result[constants.LOG_KEY_ACTION] = "noop"
    return result

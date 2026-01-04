from __future__ import annotations

from typing import Dict, Optional

from . import constants, crypto_engine

from . import constants


def _get(dev: Dict[str, str], key: str) -> Optional[str]:
    return dev.get(key) or dev.get(key.lower())


def is_usb_storage(dev: Dict[str, str]) -> bool:
    if _get(dev, "ID_BUS") != "usb":
        return False
    dev_type = _get(dev, "ID_TYPE")
    return dev_type in ("disk", "partition")


def is_partition(dev: Dict[str, str]) -> bool:
    return _get(dev, "DEVTYPE") == "partition"


def is_mapper(dev: Dict[str, str]) -> bool:
    return _get(dev, "DM_UUID") is not None or _get(dev, "DM_NAME") is not None


def classify_device(dev: Dict[str, str], devnode: Optional[str] = None) -> str:
    if is_mapper(dev):
        return constants.MAPPER
    fs_type = _get(dev, "ID_FS_TYPE")
    luks_version = _get(dev, "ID_FS_VERSION")
    if fs_type == "crypto_LUKS":
        if luks_version == "2":
            return constants.LUKS2_LOCKED
        if devnode:
            detected = crypto_engine.luks_version(devnode)
            if detected == "2":
                return constants.LUKS2_LOCKED
        return constants.LUKS1
    if is_usb_storage(dev):
        return constants.PLAINTEXT
    return constants.UNKNOWN

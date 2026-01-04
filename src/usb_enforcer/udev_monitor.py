from __future__ import annotations

import logging
from typing import Callable, Dict

import pyudev


def start_monitor(callback: Callable[[Dict[str, str], str, str], None], logger: logging.Logger) -> None:
    """
    Start udev monitor and invoke callback(device_props, devnode, action).
    """
    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by("block")
    logger.info("Starting udev monitor for block devices")
    for device in iter(monitor.poll, None):
        try:
            devnode = device.device_node
            if not devnode:
                continue
            action = device.action or "change"
            callback(dict(device), devnode, action)
        except Exception as exc:  # pragma: no cover
            logger.exception("Error handling udev event: %s", exc)

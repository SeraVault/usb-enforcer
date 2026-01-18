from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

try:
    import pydbus
except ImportError:  # pragma: no cover
    pydbus = None
try:
    from pydbus.generic import signal as dbus_signal
except Exception:  # pragma: no cover
    dbus_signal = None


DBUS_NAME = "org.seravault.UsbEnforcer"
DBUS_PATH = "/org/seravault/UsbEnforcer"


class UsbEnforcerDBus:
    """
    <node>
      <interface name='org.seravault.UsbEnforcer'>
        <method name='ListDevices'>
          <arg type='aa{ss}' name='devices' direction='out'/>
        </method>
        <method name='GetDeviceStatus'>
          <arg type='s' name='devnode' direction='in'/>
          <arg type='a{ss}' name='status' direction='out'/>
        </method>
        <method name='RequestUnlock'>
          <arg type='s' name='devnode' direction='in'/>
          <arg type='s' name='mapper_name' direction='in'/>
          <arg type='s' name='token' direction='in'/>
          <arg type='s' name='result' direction='out'/>
        </method>
        <method name='RequestEncrypt'>
          <arg type='s' name='devnode' direction='in'/>
          <arg type='s' name='mapper_name' direction='in'/>
          <arg type='s' name='token' direction='in'/>
          <arg type='s' name='fs_type' direction='in'/>
          <arg type='s' name='label' direction='in'/>
          <arg type='s' name='result' direction='out'/>
        </method>
        <method name='GetScannerStatistics'>
          <arg type='a{ss}' name='statistics' direction='out'/>
        </method>
        <signal name='Event'>
          <arg type='a{ss}' name='fields'/>
        </signal>
        <signal name='ScanProgress'>
          <arg type='s' name='filepath'/>
          <arg type='d' name='progress'/>
          <arg type='s' name='status'/>
          <arg type='x' name='total_size'/>
          <arg type='x' name='scanned_size'/>
        </signal>
        <signal name='ContentBlocked'>
          <arg type='s' name='filepath'/>
          <arg type='s' name='reason'/>
          <arg type='s' name='patterns'/>
          <arg type='i' name='match_count'/>
        </signal>
      </interface>
    </node>
    """

    def __init__(
        self,
        logger: logging.Logger,
        list_devices_func: Callable[[], List[Dict[str, str]]],
        get_status_func: Callable[[str], Dict[str, str]],
        unlock_func: Callable[[str, str, str], str],
        encrypt_func: Callable[[str, str, str, str, Optional[str]], str],
        get_scanner_stats_func: Optional[Callable[[], Dict[str, str]]] = None,
    ):
        self.logger = logger
        self.list_devices_func = list_devices_func
        self.get_status_func = get_status_func
        self.unlock_func = unlock_func
        self.encrypt_func = encrypt_func
        self.get_scanner_stats_func = get_scanner_stats_func
        self.bus: Optional[Any] = None
        self._event_subscribers: List[Any] = []

    # pydbus signal definitions
    Event = dbus_signal() if dbus_signal else None
    ScanProgress = dbus_signal() if dbus_signal else None
    ContentBlocked = dbus_signal() if dbus_signal else None

    def Export(self):  # noqa: N802
        """
        Export on DBus if pydbus/system bus available.
        """
        if not pydbus:
            self.logger.warning("pydbus not available; DBus API disabled")
            return None
        try:
            bus = pydbus.SystemBus()
            bus.publish(DBUS_NAME, self)
            self.logger.info("DBus service published at %s %s", DBUS_NAME, DBUS_PATH)
            self.bus = bus
            return self.bus
        except Exception as e:
            self.logger.error("Failed to publish DBus service: %s", e)
            self.logger.warning("DBus API disabled due to connection failure")
            return None

    # DBus-exposed methods
    def ListDevices(self) -> List[Dict[str, str]]:  # noqa: N802
        return self.list_devices_func()

    def GetDeviceStatus(self, devnode: str) -> Dict[str, str]:  # noqa: N802
        return self.get_status_func(devnode)

    def RequestUnlock(self, devnode: str, mapper_name: str, token: str) -> str:  # noqa: N802
        return self.unlock_func(devnode, mapper_name, token)

    def RequestEncrypt(self, devnode: str, mapper_name: str, token: str, fs_type: str, label: str) -> str:  # noqa: N802
        return self.encrypt_func(devnode, mapper_name, token, fs_type, label or None)
    
    def GetScannerStatistics(self) -> Dict[str, str]:  # noqa: N802
        """Get content scanner statistics"""
        if self.get_scanner_stats_func:
            return self.get_scanner_stats_func()
        return {}

    # Events: emit dict fields to listeners
    def emit_event(self, fields: Dict[str, str]) -> None:
        if not self.bus or not dbus_signal:
            return
        try:
            self.Event(fields)
        except Exception:  # pragma: no cover
            self.logger.exception("Failed to emit Event signal")
    
    def emit_scan_progress(self, filepath: str, progress: float, status: str,
                          total_size: int, scanned_size: int) -> None:
        """Emit scan progress signal for GUI notifications"""
        if not self.bus or not dbus_signal:
            return
        try:
            self.ScanProgress(filepath, progress, status, total_size, scanned_size)
        except Exception:  # pragma: no cover
            self.logger.exception("Failed to emit ScanProgress signal")
    
    def emit_content_blocked(self, filepath: str, reason: str, patterns: str, match_count: int) -> None:
        """Emit content blocked signal for GUI notifications"""
        if not self.bus or not dbus_signal:
            return
        try:
            self.ContentBlocked(filepath, reason, patterns, match_count)
        except Exception:  # pragma: no cover
            self.logger.exception("Failed to emit ContentBlocked signal")

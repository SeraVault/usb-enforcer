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


DBUS_NAME = "org.seravault.UsbEncryptionEnforcer"
DBUS_PATH = "/org/seravault/UsbEncryptionEnforcer"


class UsbEncryptionEnforcerDBus:
    """
    <node>
      <interface name='org.seravault.UsbEncryptionEnforcer'>
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
          <arg type='s' name='passphrase' direction='in'/>
          <arg type='s' name='result' direction='out'/>
        </method>
        <method name='RequestEncrypt'>
          <arg type='s' name='devnode' direction='in'/>
          <arg type='s' name='mapper_name' direction='in'/>
          <arg type='s' name='passphrase' direction='in'/>
          <arg type='s' name='fs_type' direction='in'/>
          <arg type='s' name='label' direction='in'/>
          <arg type='s' name='result' direction='out'/>
        </method>
        <signal name='Event'>
          <arg type='a{ss}' name='fields'/>
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
    ):
        self.logger = logger
        self.list_devices_func = list_devices_func
        self.get_status_func = get_status_func
        self.unlock_func = unlock_func
        self.encrypt_func = encrypt_func
        self.bus: Optional[Any] = None
        self._event_subscribers: List[Any] = []

    # pydbus signal definition
    Event = dbus_signal() if dbus_signal else None

    def Export(self):  # noqa: N802
        """
        Export on DBus if pydbus/system bus available.
        """
        if not pydbus:
            self.logger.warning("pydbus not available; DBus API disabled")
            return None
        bus = pydbus.SystemBus()
        bus.publish(DBUS_NAME, self)
        self.logger.info("DBus service published at %s %s", DBUS_NAME, DBUS_PATH)
        self.bus = bus
        return self.bus

    # DBus-exposed methods
    def ListDevices(self) -> List[Dict[str, str]]:  # noqa: N802
        return self.list_devices_func()

    def GetDeviceStatus(self, devnode: str) -> Dict[str, str]:  # noqa: N802
        return self.get_status_func(devnode)

    def RequestUnlock(self, devnode: str, mapper_name: str, passphrase: str) -> str:  # noqa: N802
        return self.unlock_func(devnode, mapper_name, passphrase)

    def RequestEncrypt(self, devnode: str, mapper_name: str, passphrase: str, fs_type: str, label: str) -> str:  # noqa: N802
        return self.encrypt_func(devnode, mapper_name, passphrase, fs_type, label or None)

    # Events: emit dict fields to listeners
    def emit_event(self, fields: Dict[str, str]) -> None:
        if not self.bus or not dbus_signal:
            return
        try:
            self.Event(fields)
        except Exception:  # pragma: no cover
            self.logger.exception("Failed to emit Event signal")

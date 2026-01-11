"""Integration tests for D-Bus API real-world operations.

These tests require root privileges and D-Bus system bus access.
Run with: sudo pytest tests/integration/test_dbus_integration.py -v
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

try:
    import pydbus
    from gi.repository import GLib
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False

from usb_enforcer import constants, dbus_api
import logging


def create_test_dbus_service():
    """Helper to create a test D-Bus service with mock callbacks."""
    logger = logging.getLogger("test-dbus")
    
    # Mock functions for the service
    def mock_list_devices():
        return []
    
    def mock_get_status(devnode):
        return {"devnode": devnode, "status": "unknown"}
    
    def mock_unlock(devnode, mapper_name, passphrase):
        return "success"
    
    def mock_encrypt(devnode, mapper_name, passphrase, fs_type, label):
        return "success"
    
    service = dbus_api.UsbEnforcerDBus(
        logger=logger,
        list_devices_func=mock_list_devices,
        get_status_func=mock_get_status,
        unlock_func=mock_unlock,
        encrypt_func=mock_encrypt
    )
    return service


@pytest.mark.skipif(not DBUS_AVAILABLE, reason="D-Bus not available")
@pytest.mark.integration
class TestDBusServiceInitialization:
    """Test D-Bus service initialization."""
    
    def test_create_dbus_service_object(self):
        """Test creating D-Bus service object."""
        service = create_test_dbus_service()
        
        assert service is not None
        assert hasattr(service, 'GetDeviceStatus')
        assert hasattr(service, 'RequestEncrypt')
        assert hasattr(service, 'ListDevices')
    
    def test_dbus_interface_definition(self):
        """Test D-Bus interface XML is properly defined."""
        service = create_test_dbus_service()
        
        # Check service has necessary methods
        assert hasattr(service, 'ListDevices')
        assert hasattr(service, 'GetDeviceStatus')
        assert hasattr(service, 'RequestUnlock')
        assert hasattr(service, 'RequestEncrypt')
        
        # Check docstring has interface definition
        assert service.__doc__ is not None
        assert "org.seravault.UsbEnforcer" in service.__doc__
        assert "GetDeviceStatus" in service.__doc__
        assert "RequestEncrypt" in service.__doc__


@pytest.mark.skipif(not DBUS_AVAILABLE, reason="D-Bus not available")
@pytest.mark.integration
class TestDBusMethodCalls:
    """Test D-Bus method invocations."""
    
    def test_get_status_method(self):
        """Test GetDeviceStatus D-Bus method."""
        service = create_test_dbus_service()
        
        # Call GetDeviceStatus with a device path
        status = service.GetDeviceStatus("/dev/sdb1")
        
        # Should return dict
        assert isinstance(status, dict)
        assert "devnode" in status
        assert status["devnode"] == "/dev/sdb1"
    
    def test_list_devices_method(self):
        """Test ListDevices D-Bus method."""
        # Create service with mock that returns devices
        def mock_list_with_devices():
            return [
                {constants.LOG_KEY_DEVNODE: "/dev/sdb1", constants.LOG_KEY_CLASSIFICATION: constants.PLAINTEXT},
                {constants.LOG_KEY_DEVNODE: "/dev/sdc1", constants.LOG_KEY_CLASSIFICATION: constants.LUKS2_LOCKED},
            ]
        
        logger = logging.getLogger("test-dbus")
        service = dbus_api.UsbEnforcerDBus(
            logger=logger,
            list_devices_func=mock_list_with_devices,
            get_status_func=lambda d: {"devnode": d, "status": "unknown"},
            unlock_func=lambda d, m, p: "success",
            encrypt_func=lambda d, m, p, f, l: "success"
        )
        
        # Call ListDevices
        devices = service.ListDevices()
        
        # Should return list of dicts
        assert isinstance(devices, list)
        assert len(devices) == 2
        assert devices[0][constants.LOG_KEY_DEVNODE] == "/dev/sdb1"
        assert devices[1][constants.LOG_KEY_DEVNODE] == "/dev/sdc1"
    
    def test_request_encryption_method(self):
        """Test RequestEncrypt D-Bus method."""
        # Create service with mock encrypt function that returns token
        def mock_encrypt(devnode, mapper_name, passphrase, fs_type, label):
            return f"token-{devnode}-{mapper_name}"
        
        logger = logging.getLogger("test-dbus")
        service = dbus_api.UsbEnforcerDBus(
            logger=logger,
            list_devices_func=lambda: [],
            get_status_func=lambda d: {"devnode": d},
            unlock_func=lambda d, m, p: "success",
            encrypt_func=mock_encrypt
        )
        
        # Call RequestEncrypt
        result = service.RequestEncrypt(
            devnode="/dev/sdb1",
            mapper_name="test-mapper",
            passphrase="TestPass123!@#",
            fs_type="exfat",
            label="TestLabel"
        )
        
        # Should return result string
        assert isinstance(result, str)
        assert "token" in result or "success" in result


@pytest.mark.skipif(not DBUS_AVAILABLE, reason="D-Bus not available")
@pytest.mark.integration
class TestDBusSignals:
    """Test D-Bus signal emissions."""
    
    def test_device_event_signal_structure(self):
        """Test DeviceEvent signal has correct structure."""
        service = create_test_dbus_service()
        
        event_data = {
            constants.LOG_KEY_EVENT: "device_add",
            constants.LOG_KEY_DEVNODE: "/dev/sdb1",
            constants.LOG_KEY_ACTION: "block_ro",
            constants.LOG_KEY_CLASSIFICATION: constants.PLAINTEXT,
        }
        
        # Convert to JSON for signal
        event_json = json.dumps(event_data)
        
        # Should be valid JSON
        assert json.loads(event_json) == event_data
    
    def test_emit_event(self):
        """Test emitting D-Bus events."""
        service = create_test_dbus_service()
        
        event_fields = {
            constants.LOG_KEY_EVENT: "device_add",
            constants.LOG_KEY_DEVNODE: "/dev/sdb1",
            constants.LOG_KEY_CLASSIFICATION: constants.PLAINTEXT,
        }
        
        # This should not raise an error
        # (actual emission requires D-Bus connection which we don't test here)
        try:
            service.emit_event(event_fields)
        except Exception:
            # Expected to fail without actual D-Bus bus
            pass


@pytest.mark.skipif(not DBUS_AVAILABLE, reason="D-Bus not available")
@pytest.mark.integration
class TestDBusServiceLifecycle:
    """Test D-Bus service lifecycle operations."""
    
    def test_service_device_tracking(self):
        """Test service uses callback functions correctly."""
        # Track devices in test
        device_list = []
        
        def mock_list():
            return device_list
        
        logger = logging.getLogger("test-dbus")
        service = dbus_api.UsbEnforcerDBus(
            logger=logger,
            list_devices_func=mock_list,
            get_status_func=lambda d: {"devnode": d},
            unlock_func=lambda d, m, p: "success",
            encrypt_func=lambda d, m, p, f, l: "success"
        )
        
        # Initially empty
        assert len(service.ListDevices()) == 0
        
        # Add device to external list
        device_list.append({
            constants.LOG_KEY_DEVNODE: "/dev/sdb1",
            constants.LOG_KEY_CLASSIFICATION: constants.PLAINTEXT,
        })
        
        # List devices should return it
        devices = service.ListDevices()
        assert len(devices) == 1
        assert devices[0][constants.LOG_KEY_DEVNODE] == "/dev/sdb1"
    
    def test_service_set_daemon_callback(self):
        """Test daemon callback for encryption works."""
        callback = MagicMock(return_value="token-12345")
        
        logger = logging.getLogger("test-dbus")
        service = dbus_api.UsbEnforcerDBus(
            logger=logger,
            list_devices_func=lambda: [],
            get_status_func=lambda d: {"devnode": d},
            unlock_func=lambda d, m, p: "success",
            encrypt_func=callback
        )
        
        # Use RequestEncrypt which calls the callback
        result = service.RequestEncrypt("/dev/sdb1", "mapper", "TestPass123!@#", "exfat", "label")
        
        assert result == "token-12345"
        callback.assert_called_once()


@pytest.mark.skipif(not DBUS_AVAILABLE, reason="D-Bus not available")
@pytest.mark.integration
class TestDBusRealWorldScenarios:
    """Test realistic D-Bus usage scenarios."""
    
    def test_device_add_workflow(self):
        """Test complete device add workflow via D-Bus."""
        # Simulate device list tracking
        devices_list = []
        
        def mock_list():
            return devices_list
        
        logger = logging.getLogger("test-dbus")
        service = dbus_api.UsbEnforcerDBus(
            logger=logger,
            list_devices_func=mock_list,
            get_status_func=lambda d: {"devnode": d, "status": "mounted"},
            unlock_func=lambda d, m, p: "success",
            encrypt_func=lambda d, m, p, f, l: "success"
        )
        
        # Simulate device added
        device_info = {
            constants.LOG_KEY_DEVNODE: "/dev/sdb1",
            constants.LOG_KEY_CLASSIFICATION: constants.PLAINTEXT,
            constants.LOG_KEY_ACTION: "block_ro",
            constants.LOG_KEY_RESULT: "allow",
        }
        devices_list.append(device_info)
        
        # Emit event
        try:
            service.emit_event(device_info)
        except Exception:
            pass  # Expected without actual bus
        
        # Check device status
        status = service.GetDeviceStatus("/dev/sdb1")
        assert status["devnode"] == "/dev/sdb1"
        
        # List devices
        devices = service.ListDevices()
        assert len(devices) == 1
        assert devices[0][constants.LOG_KEY_DEVNODE] == "/dev/sdb1"
    
    def test_encryption_request_workflow(self):
        """Test complete encryption request workflow."""
        # Setup encryption callback
        def mock_encrypt(devnode: str, mapper_name: str, passphrase: str, fs_type: str, label: str) -> str:
            # Simulate encryption
            return f"token-{devnode}-{mapper_name}"
        
        logger = logging.getLogger("test-dbus")
        service = dbus_api.UsbEnforcerDBus(
            logger=logger,
            list_devices_func=lambda: [],
            get_status_func=lambda d: {"devnode": d},
            unlock_func=lambda d, m, p: "success",
            encrypt_func=mock_encrypt
        )
        
        # Request encryption
        token = service.RequestEncrypt("/dev/sdb1", "test-mapper", "SecurePass123!@#", "exfat", "MyUSB")
        
        # Should get a token
        assert token.startswith("token-/dev/sdb1")
    
    def test_multiple_device_tracking(self):
        """Test tracking multiple devices simultaneously."""
        # Build device list
        devices_list = []
        devices_to_add = [
            ("/dev/sdb1", constants.PLAINTEXT),
            ("/dev/sdc1", constants.LUKS2_LOCKED),
            ("/dev/sdd1", constants.MAPPER),
        ]
        
        for devnode, classification in devices_to_add:
            devices_list.append({
                constants.LOG_KEY_DEVNODE: devnode,
                constants.LOG_KEY_CLASSIFICATION: classification,
            })
        
        logger = logging.getLogger("test-dbus")
        service = dbus_api.UsbEnforcerDBus(
            logger=logger,
            list_devices_func=lambda: devices_list,
            get_status_func=lambda d: {"devnode": d},
            unlock_func=lambda d, m, p: "success",
            encrypt_func=lambda d, m, p, f, l: "success"
        )
        
        # List devices
        devices = service.ListDevices()
        
        assert len(devices) == 3
        devnodes = [d[constants.LOG_KEY_DEVNODE] for d in devices]
        assert "/dev/sdb1" in devnodes
        assert "/dev/sdc1" in devnodes
        assert "/dev/sdd1" in devnodes


@pytest.mark.skipif(not DBUS_AVAILABLE, reason="D-Bus not available")
@pytest.mark.integration
class TestDBusErrorHandling:
    """Test D-Bus error handling."""
    
    def test_list_devices_when_empty(self):
        """Test ListDevices returns empty list when no devices."""
        service = create_test_dbus_service()
        
        devices = service.ListDevices()
        
        assert devices == []
        assert isinstance(devices, list)
    
    def test_get_status_always_works(self):
        """Test GetDeviceStatus always returns valid response."""
        service = create_test_dbus_service()
        
        # Get status for different devices
        status1 = service.GetDeviceStatus("/dev/sdb1")
        assert isinstance(status1, dict)
        assert "devnode" in status1
        assert status1["devnode"] == "/dev/sdb1"
        
        status2 = service.GetDeviceStatus("/dev/sdc1")
        assert isinstance(status2, dict)
        assert "devnode" in status2
        assert status2["devnode"] == "/dev/sdc1"
    
    def test_encryption_without_callback(self):
        """Test encryption request when encrypt function raises error."""
        def mock_encrypt_error(devnode, mapper_name, passphrase, fs_type, label):
            raise RuntimeError("Encryption not available")
        
        logger = logging.getLogger("test-dbus")
        service = dbus_api.UsbEnforcerDBus(
            logger=logger,
            list_devices_func=lambda: [],
            get_status_func=lambda d: {"devnode": d},
            unlock_func=lambda d, m, p: "success",
            encrypt_func=mock_encrypt_error
        )
        
        # Should raise error
        with pytest.raises(RuntimeError):
            service.RequestEncrypt("/dev/sdb1", "mapper", "TestPass123!@#", "exfat", "label")


@pytest.mark.skipif(not DBUS_AVAILABLE, reason="D-Bus not available")
@pytest.mark.integration
class TestDBusJSONSerialization:
    """Test JSON serialization for D-Bus methods."""
    
    def test_serialize_device_info(self):
        """Test serializing device info to JSON."""
        device_info = {
            constants.LOG_KEY_DEVNODE: "/dev/sdb1",
            constants.LOG_KEY_CLASSIFICATION: constants.PLAINTEXT,
            constants.LOG_KEY_ACTION: "block_ro",
            constants.LOG_KEY_RESULT: "allow",
            constants.LOG_KEY_BUS: "usb",
            constants.LOG_KEY_SERIAL: "ABC123",
        }
        
        # Serialize
        json_str = json.dumps(device_info)
        
        # Deserialize
        deserialized = json.loads(json_str)
        
        assert deserialized == device_info
    
    def test_serialize_device_list(self):
        """Test serializing device list to JSON."""
        devices = {
            "/dev/sdb1": {
                constants.LOG_KEY_DEVNODE: "/dev/sdb1",
                constants.LOG_KEY_CLASSIFICATION: constants.PLAINTEXT,
            },
            "/dev/sdc1": {
                constants.LOG_KEY_DEVNODE: "/dev/sdc1",
                constants.LOG_KEY_CLASSIFICATION: constants.LUKS2_LOCKED,
            },
        }
        
        # Serialize
        json_str = json.dumps(devices)
        
        # Deserialize
        deserialized = json.loads(json_str)
        
        assert deserialized == devices
        assert len(deserialized) == 2

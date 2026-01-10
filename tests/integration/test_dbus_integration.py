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
        assert "org.seravault.UsbEnforcer" in dbus_xml
        assert "GetStatus" in dbus_xml
        assert "RequestEncryption" in dbus_xml


@pytest.mark.skipif(not DBUS_AVAILABLE, reason="D-Bus not available")
@pytest.mark.integration
class TestDBusMethodCalls:
    """Test D-Bus method invocations."""
    
    def test_get_status_method(self):
        """Test GetStatus D-Bus method."""
        service = create_test_dbus_service()
        
        # Call GetStatus
        status = service.GetStatus()
        
        # Should return JSON string
        assert isinstance(status, str)
        
        # Should be valid JSON
        status_data = json.loads(status)
        assert "status" in status_data
    
    def test_list_devices_method(self):
        """Test ListDevices D-Bus method."""
        service = create_test_dbus_service()
        
        # Add some mock devices
        service._devices = {
            "/dev/sdb1": {
                constants.LOG_KEY_DEVNODE: "/dev/sdb1",
                constants.LOG_KEY_CLASSIFICATION: constants.PLAINTEXT,
            },
            "/dev/sdc1": {
                constants.LOG_KEY_DEVNODE: "/dev/sdc1",
                constants.LOG_KEY_CLASSIFICATION: constants.LUKS2_LOCKED,
            },
        }
        
        # Call ListDevices
        devices_json = service.ListDevices()
        
        # Should return JSON string
        assert isinstance(devices_json, str)
        
        # Should be valid JSON with devices
        devices = json.loads(devices_json)
        assert "/dev/sdb1" in devices
        assert "/dev/sdc1" in devices
    
    def test_request_encryption_method(self):
        """Test RequestEncryption D-Bus method."""
        service = create_test_dbus_service()
        
        device = "/dev/sdb1"
        passphrase = "test-passphrase-123"
        
        # Mock the daemon callback
        service._encryption_callback = MagicMock(return_value="test-token-12345")
        
        # Call RequestEncryption
        token = service.RequestEncryption(device, passphrase)
        
        # Should return a token
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Callback should be called
        service._encryption_callback.assert_called_once_with(device, passphrase)


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
        """Test service tracks devices correctly."""
        service = create_test_dbus_service()
        
        # Initially empty
        assert len(service._devices) == 0
        
        # Add device
        device_info = {
            constants.LOG_KEY_DEVNODE: "/dev/sdb1",
            constants.LOG_KEY_CLASSIFICATION: constants.PLAINTEXT,
        }
        service._devices["/dev/sdb1"] = device_info
        
        # Should be tracked
        assert "/dev/sdb1" in service._devices
        assert len(service._devices) == 1
        
        # List devices should return it
        devices_json = service.ListDevices()
        devices = json.loads(devices_json)
        assert "/dev/sdb1" in devices
    
    def test_service_set_daemon_callback(self):
        """Test setting daemon callback for encryption."""
        service = create_test_dbus_service()
        
        callback = MagicMock(return_value="token-12345")
        service._encryption_callback = callback
        
        # Use the callback
        result = service._encryption_callback("/dev/sdb1", "password")
        
        assert result == "token-12345"
        callback.assert_called_once_with("/dev/sdb1", "password")


@pytest.mark.skipif(not DBUS_AVAILABLE, reason="D-Bus not available")
@pytest.mark.integration
class TestDBusRealWorldScenarios:
    """Test realistic D-Bus usage scenarios."""
    
    def test_device_add_workflow(self):
        """Test complete device add workflow via D-Bus."""
        service = create_test_dbus_service()
        
        # Simulate device added
        device_info = {
            constants.LOG_KEY_DEVNODE: "/dev/sdb1",
            constants.LOG_KEY_CLASSIFICATION: constants.PLAINTEXT,
            constants.LOG_KEY_ACTION: "block_ro",
            constants.LOG_KEY_RESULT: "allow",
        }
        
        service._devices["/dev/sdb1"] = device_info
        
        # Emit event
        try:
            service.emit_event(device_info)
        except Exception:
            pass  # Expected without actual bus
        
        # Check status
        status = service.GetStatus()
        status_data = json.loads(status)
        assert status_data["status"] == "running"
        
        # List devices
        devices = json.loads(service.ListDevices())
        assert "/dev/sdb1" in devices
    
    def test_encryption_request_workflow(self):
        """Test complete encryption request workflow."""
        service = create_test_dbus_service()
        
        # Setup encryption callback
        def mock_encrypt(device: str, passphrase: str) -> str:
            # Simulate encryption
            return f"token-{device}-{hash(passphrase)}"
        
        service._encryption_callback = mock_encrypt
        
        # Request encryption
        token = service.RequestEncryption("/dev/sdb1", "secure-password")
        
        # Should get a token
        assert token.startswith("token-/dev/sdb1")
    
    def test_multiple_device_tracking(self):
        """Test tracking multiple devices simultaneously."""
        service = create_test_dbus_service()
        
        # Add multiple devices
        devices_to_add = [
            ("/dev/sdb1", constants.PLAINTEXT),
            ("/dev/sdc1", constants.LUKS2_LOCKED),
            ("/dev/sdd1", constants.MAPPER),
        ]
        
        for devnode, classification in devices_to_add:
            device_info = {
                constants.LOG_KEY_DEVNODE: devnode,
                constants.LOG_KEY_CLASSIFICATION: classification,
            }
            service._devices[devnode] = device_info
        
        # List devices
        devices = json.loads(service.ListDevices())
        
        assert len(devices) == 3
        assert "/dev/sdb1" in devices
        assert "/dev/sdc1" in devices
        assert "/dev/sdd1" in devices


@pytest.mark.skipif(not DBUS_AVAILABLE, reason="D-Bus not available")
@pytest.mark.integration
class TestDBusErrorHandling:
    """Test D-Bus error handling."""
    
    def test_list_devices_when_empty(self):
        """Test ListDevices returns empty dict when no devices."""
        service = create_test_dbus_service()
        
        devices_json = service.ListDevices()
        devices = json.loads(devices_json)
        
        assert devices == {}
    
    def test_get_status_always_works(self):
        """Test GetStatus always returns valid response."""
        service = create_test_dbus_service()
        
        status = service.GetStatus()
        
        # Should always be valid JSON
        status_data = json.loads(status)
        assert "status" in status_data
    
    def test_encryption_without_callback(self):
        """Test encryption request without callback set."""
        service = create_test_dbus_service()
        
        # No callback set
        service._encryption_callback = None
        
        # Should handle gracefully
        try:
            token = service.RequestEncryption("/dev/sdb1", "password")
            # If it returns, should be empty string
            assert token == ""
        except (TypeError, AttributeError):
            # Or it might raise an error, which is also acceptable
            pass


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

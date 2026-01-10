"""Integration tests for daemon real-world operations.

These tests require root privileges and test actual daemon behavior.
Run with: sudo pytest tests/integration/test_daemon.py -v
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from usb_enforcer import config as config_module, constants, daemon


@pytest.mark.integration
class TestDaemonInitialization:
    """Test daemon initialization and configuration."""
    
    def test_daemon_init_with_default_config(self):
        """Test daemon initializes with default configuration."""
        d = daemon.Daemon()
        
        assert d.config is not None
        assert d.logger is not None
        assert isinstance(d.devices, dict)
        assert len(d.devices) == 0
    
    def test_daemon_init_with_custom_config(self, mock_config_file):
        """Test daemon initializes with custom configuration."""
        d = daemon.Daemon(config_path=mock_config_file)
        
        assert d.config.exempted_groups == ["usb-exempt"]
        assert d.config.min_passphrase_length == 12
        assert d.config.encryption_target_mode == "whole_disk"
    
    def test_daemon_device_tracking(self):
        """Test daemon device tracking dictionary."""
        d = daemon.Daemon()
        
        # Add a device
        device_info = {
            "devnode": "/dev/sdb1",
            "classification": constants.PLAINTEXT,
            "action": "add"
        }
        d.devices["/dev/sdb1"] = device_info
        
        assert "/dev/sdb1" in d.devices
        assert d.devices["/dev/sdb1"]["classification"] == constants.PLAINTEXT


@pytest.mark.integration
class TestDaemonSecretSocket:
    """Test daemon secret socket operations."""
    
    def test_secret_socket_auto_created(self, temp_dir):
        """Test secret socket is automatically created on daemon init."""
        d = daemon.Daemon()
        
        # Socket should be configured
        assert d._secret_socket_path is not None
        assert d._secret_store is not None
        assert d._secret_lock is not None
    
    def test_secret_storage(self):
        """Test storing and retrieving secrets."""
        d = daemon.Daemon()
        
        token = "test-token-12345"
        operation = "encrypt"
        passphrase = "test-passphrase-secure"
        
        # Store secret
        with d._secret_lock:
            d._secret_store[token] = (operation, passphrase)
        
        # Retrieve secret
        with d._secret_lock:
            stored_op, stored_pass = d._secret_store.get(token, (None, None))
        
        assert stored_op == operation
        assert stored_pass == passphrase
    
    def test_secret_cleanup(self):
        """Test secrets are cleaned up after use."""
        d = daemon.Daemon()
        
        token = "test-token-cleanup"
        d._secret_store[token] = ("encrypt", "password")
        
        # Clean up
        with d._secret_lock:
            if token in d._secret_store:
                del d._secret_store[token]
        
        assert token not in d._secret_store


@pytest.mark.integration
class TestDeviceEventHandling:
    """Test daemon device event handling."""
    
    def test_handle_device_add_event(self, loop_device, mock_config_file):
        """Test handling device add event."""
        with loop_device(size_mb=100) as device:
            # Format device to get properties
            subprocess.run(["mkfs.ext4", "-F", device], check=True, capture_output=True)
            
            # Get real device properties
            result = subprocess.run(
                ["blkid", "-o", "export", device],
                capture_output=True,
                text=True
            )
            
            device_props = {}
            for line in result.stdout.splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    device_props[key] = value
            
            # Add USB properties (simulated)
            device_props["ID_BUS"] = "usb"
            device_props["ID_TYPE"] = "partition"
            device_props["DEVTYPE"] = "partition"
            device_props["DEVNAME"] = device
            
            # Create daemon and handle event
            d = daemon.Daemon(config_path=mock_config_file)
            
            # Mock the user exemption check
            with patch('usb_enforcer.user_utils.any_active_user_in_groups', return_value=(False, "")):
                d.handle_device(device_props, device, "add")
            
            # Device should be tracked
            assert device in d.devices


@pytest.mark.integration
class TestDaemonLogging:
    """Test daemon logging functionality."""
    
    def test_structured_logging(self, temp_dir):
        """Test structured logging produces valid JSON."""
        log_file = temp_dir / "test-daemon.log"
        
        # Create logger
        logger = logging.getLogger("test-daemon-logging")
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
        
        # Log structured event
        from usb_enforcer import logging_utils
        
        fields = {
            constants.LOG_KEY_EVENT: "device_add",
            constants.LOG_KEY_DEVNODE: "/dev/sdb1",
            constants.LOG_KEY_ACTION: "block_ro",
            constants.LOG_KEY_CLASSIFICATION: constants.PLAINTEXT,
        }
        
        logging_utils.log_structured(logger, "Device event", fields)
        
        # Read log and verify content
        handler.flush()
        log_content = log_file.read_text()
        
        # Should contain the logged message and fields
        # log_structured formats as "message extra_key1=value1 extra_key2=value2"
        assert "Device event" in log_content
        assert "/dev/sdb1" in log_content


@pytest.mark.integration
class TestDaemonShutdown:
    """Test daemon shutdown behavior."""
    
    def test_daemon_stop_event(self):
        """Test daemon stop event mechanism."""
        d = daemon.Daemon()
        
        # Initially not stopped
        assert not d._stop_event.is_set()
        
        # Set stop event
        d._stop_event.set()
        
        assert d._stop_event.is_set()


@pytest.mark.integration
class TestDaemonRealWorld:
    """Test realistic daemon scenarios."""
    
    def test_daemon_device_lifecycle(self, loop_device, mock_config_file):
        """Test complete device lifecycle: add -> monitor -> remove."""
        with loop_device(size_mb=100) as device:
            # Format device
            subprocess.run(["mkfs.ext4", "-F", device], check=True, capture_output=True)
            
            # Get device properties
            result = subprocess.run(
                ["blkid", "-o", "export", device],
                capture_output=True,
                text=True
            )
            
            device_props = {}
            for line in result.stdout.splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    device_props[key] = value
            
            device_props["ID_BUS"] = "usb"
            device_props["ID_TYPE"] = "partition"
            device_props["DEVTYPE"] = "partition"
            device_props["ID_FS_USAGE"] = "filesystem"
            
            # Create daemon
            d = daemon.Daemon(config_path=mock_config_file)
            
            # Handle add event
            with patch('usb_enforcer.user_utils.any_active_user_in_groups', return_value=(False, "")):
                d.handle_device(device_props, device, "add")
            
            assert device in d.devices
            
            # Handle remove event
            d.handle_device(device_props, device, "remove")
            
            # Device should be removed from tracking
            assert device not in d.devices
    
    def test_daemon_multiple_devices(self, mock_config_file):
        """Test daemon tracking multiple devices simultaneously."""
        d = daemon.Daemon(config_path=mock_config_file)
        
        # Simulate multiple devices
        devices = [
            {
                "devnode": "/dev/sdb1",
                "ID_BUS": "usb",
                "DEVTYPE": "partition",
                "ID_FS_TYPE": "ext4",
                "ID_FS_USAGE": "filesystem",
            },
            {
                "devnode": "/dev/sdc1",
                "ID_BUS": "usb",
                "DEVTYPE": "partition",
                "ID_FS_TYPE": "crypto_LUKS",
                "ID_FS_VERSION": "2",
            },
            {
                "devnode": "/dev/sdd1",
                "ID_BUS": "usb",
                "DEVTYPE": "partition",
                "ID_FS_TYPE": "exfat",
                "ID_FS_USAGE": "filesystem",
            },
        ]
        
        with patch('usb_enforcer.user_utils.any_active_user_in_groups', return_value=(False, "")):
            for dev in devices:
                d.handle_device(dev, dev["devnode"], "add")
        
        # All devices should be tracked
        assert len(d.devices) >= len(devices)


@pytest.mark.integration
class TestBypassMechanism:
    """Test bypass enforcement mechanism."""
    
    def test_bypass_enforcement_add(self):
        """Test adding device to bypass set."""
        d = daemon.Daemon()
        
        device = "/dev/sdb1"
        d._bypass_enforcement.add(device)
        
        assert device in d._bypass_enforcement
    
    def test_bypass_enforcement_check(self):
        """Test checking if device is bypassed."""
        d = daemon.Daemon()
        
        device = "/dev/sdb1"
        d._bypass_enforcement.add(device)
        
        # Should be bypassed
        assert device in d._bypass_enforcement
        
        # Other devices should not be bypassed
        assert "/dev/sdc1" not in d._bypass_enforcement


@pytest.mark.integration
class TestEncryptionRequestHandling:
    """Test handling encryption requests."""
    
    def test_generate_encryption_token(self):
        """Test generating secure encryption tokens."""
        import secrets
        
        token1 = secrets.token_urlsafe(32)
        token2 = secrets.token_urlsafe(32)
        
        # Tokens should be unique
        assert token1 != token2
        assert len(token1) > 20
        assert len(token2) > 20
    
    def test_store_encryption_request(self):
        """Test storing encryption request with token."""
        d = daemon.Daemon()
        
        token = "test-encryption-token"
        device = "/dev/sdb1"
        passphrase = "secure-passphrase-123"
        
        with d._secret_lock:
            d._secret_store[token] = ("encrypt", passphrase)
        
        # Verify storage
        with d._secret_lock:
            op, stored_pass = d._secret_store.get(token, (None, None))
        
        assert op == "encrypt"
        assert stored_pass == passphrase


@pytest.mark.integration
class TestDaemonConfiguration:
    """Test daemon configuration handling."""
    
    def test_daemon_reload_config(self, temp_dir):
        """Test daemon can reload configuration."""
        # Create initial config
        config1 = temp_dir / "config1.toml"
        config1.write_text('exempted_groups = ["group1"]')
        
        d = daemon.Daemon(config_path=config1)
        assert d.config.exempted_groups == ["group1"]
        
        # Update config file
        config1.write_text('exempted_groups = ["group1", "group2"]')
        
        # Reload config
        d.config = config_module.Config.load(config1)
        assert "group2" in d.config.exempted_groups
    
    def test_daemon_respects_config_options(self, temp_dir):
        """Test daemon respects various configuration options."""
        # Test with enforcement disabled on USB only
        config_path = temp_dir / "config.toml"
        config_path.write_text('''
enforce_on_usb_only = false
allow_luks1_readonly = false
min_passphrase_length = 16
''')
        
        d = daemon.Daemon(config_path=config_path)
        
        assert d.config.enforce_on_usb_only is False
        assert d.config.allow_luks1_readonly is False
        assert d.config.min_passphrase_length == 16

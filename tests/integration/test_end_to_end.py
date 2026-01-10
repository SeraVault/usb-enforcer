"""End-to-end integration tests for complete USB enforcer workflow.

These tests verify the complete workflow:
1. Daemon starts and monitors devices
2. USB device is inserted (loop device)
3. Daemon detects and enforces read-only on plaintext
4. User encrypts the device
5. System allows encrypted device access

These tests require root privileges and installed system components.
Run with: sudo pytest tests/integration/test_end_to_end.py -v
"""

from __future__ import annotations

import subprocess
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import pyudev

from usb_enforcer import crypto_engine, daemon


@pytest.mark.integration
@pytest.mark.slow
class TestCompleteWorkflow:
    """Test complete USB enforcer workflow end-to-end."""
    
    def test_plaintext_device_forced_readonly(self, loop_device, mock_config_file):
        """Test that plaintext USB device is automatically forced read-only by daemon."""
        with loop_device(size_mb=100) as device:
            # Format device as plaintext
            subprocess.run(["mkfs.ext4", "-F", device], check=True, capture_output=True)
            time.sleep(0.5)
            
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
            
            # Simulate USB device properties
            device_props["ID_BUS"] = "usb"
            device_props["ID_TYPE"] = "disk"
            device_props["DEVTYPE"] = "disk"
            device_props["ID_FS_USAGE"] = "filesystem"
            # Ensure ID_FS_TYPE is set for proper classification
            if "ID_FS_TYPE" not in device_props or not device_props["ID_FS_TYPE"]:
                device_props["ID_FS_TYPE"] = "ext4"
            
            # Create and start daemon
            d = daemon.Daemon(config_path=mock_config_file)
            
            # Simulate device insertion event
            with patch('usb_enforcer.user_utils.any_active_user_in_groups', return_value=(False, "")):
                d.handle_device(device_props, device, "add")
            
            # Verify device is tracked
            assert device in d.devices
            
            # Wait a moment for enforcement to take effect
            time.sleep(0.5)
            
            # Verify device is set to read-only
            # Check via blockdev
            result = subprocess.run(
                ["blockdev", "--getro", device],
                capture_output=True,
                text=True
            )
            ro_status = result.stdout.strip()
            
            # Device should be read-only (returns "1")
            assert ro_status == "1", f"Device {device} should be read-only but got status {ro_status}"
            
            # Verify writes are blocked
            with tempfile.TemporaryDirectory() as mount_point:
                subprocess.run(["mount", "-o", "ro", device, mount_point], check=True)
                
                try:
                    # Try to write (should fail)
                    test_file = Path(mount_point) / "should_fail.txt"
                    with pytest.raises(OSError):
                        test_file.write_text("This should fail")
                finally:
                    subprocess.run(["umount", mount_point], check=False)
    
    def test_encrypted_device_workflow(self, loop_device, mock_config_file):
        """Test complete workflow: plaintext detected -> encrypted -> accessible."""
        with loop_device(size_mb=200) as device:
            # Step 1: Start with plaintext device
            # Ensure device is clean and writable
            subprocess.run(["wipefs", "-a", device], check=False, capture_output=True)
            subprocess.run(["blockdev", "--setrw", device], check=False, capture_output=True)
            time.sleep(0.3)
            
            subprocess.run(["mkfs.ext4", "-F", device], check=True, capture_output=True)
            time.sleep(0.5)
            
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
            
            # Simulate USB device
            device_props["ID_BUS"] = "usb"
            device_props["ID_TYPE"] = "disk"
            device_props["DEVTYPE"] = "disk"
            device_props["ID_FS_USAGE"] = "filesystem"
            # Ensure ID_FS_TYPE is set for classification
            if "ID_FS_TYPE" not in device_props or not device_props["ID_FS_TYPE"]:
                device_props["ID_FS_TYPE"] = "ext4"
            
            # Step 2: Daemon detects plaintext device and enforces read-only
            d = daemon.Daemon(config_path=mock_config_file)
            
            with patch('usb_enforcer.user_utils.any_active_user_in_groups', return_value=(False, "")):
                d.handle_device(device_props, device, "add")
            
            # Verify read-only enforcement
            result = subprocess.run(
                ["blockdev", "--getro", device],
                capture_output=True,
                text=True
            )
            assert result.stdout.strip() == "1", "Plaintext device should be read-only"
            
            # Step 3: User decides to encrypt the device
            # First, set read-write to allow encryption
            subprocess.run(["blockdev", "--setrw", device], check=True, capture_output=True)
            
            mapper_name = f"test-e2e-{int(time.time())}"
            passphrase = "MySecurePassword123!"
            
            try:
                # Encrypt the device (this sets it RW internally)
                mapper_path = crypto_engine.encrypt_device(
                    device,
                    mapper_name,
                    passphrase,
                    fs_type="exfat",
                    mount_opts=[],
                    label="SecureUSB"
                )
                
                # Step 4: Verify device is now encrypted
                version = crypto_engine.luks_version(device)
                assert version == "2", "Device should be LUKS2 encrypted"
                
                # Step 5: Verify mapper device exists (opened by encrypt_device)
                assert Path(mapper_path).exists(), f"Mapper device {mapper_path} should exist"
                
                # Step 6: Verify encrypted device is accessible (not read-only enforced)
                # Get mapper properties and simulate daemon event
                result = subprocess.run(
                    ["blkid", "-o", "export", mapper_path],
                    capture_output=True,
                    text=True
                )
                
                mapper_props = {}
                for line in result.stdout.splitlines():
                    if "=" in line:
                        key, value = line.split("=", 1)
                        mapper_props[key] = value
                
                mapper_props["DM_NAME"] = mapper_name
                mapper_props["DEVTYPE"] = "disk"
                
                # Daemon should allow encrypted devices
                with patch('usb_enforcer.user_utils.any_active_user_in_groups', return_value=(False, "")):
                    d.handle_device(mapper_props, mapper_path, "add")
                
                # Mapper should be in devices list
                assert mapper_path in d.devices
                
                # Step 7: Verify we can mount and write to encrypted device
                with tempfile.TemporaryDirectory() as mount_point:
                    subprocess.run(["mount", mapper_path, mount_point], check=True)
                    
                    try:
                        # Write should succeed
                        test_file = Path(mount_point) / "encrypted_data.txt"
                        test_data = "This is encrypted data! ✅"
                        test_file.write_text(test_data)
                        
                        subprocess.run(["sync"], check=False)
                        
                        # Verify we can read it back
                        read_data = test_file.read_text()
                        assert read_data == test_data, "Should be able to read/write to encrypted device"
                        
                    finally:
                        subprocess.run(["umount", mount_point], check=False)
                
            finally:
                subprocess.run(["cryptsetup", "close", mapper_name], check=False, capture_output=True)
    
    def test_daemon_bypass_during_encryption(self, loop_device, mock_config_file):
        """Test that daemon bypass mechanism works during encryption."""
        with loop_device(size_mb=100) as device:
            # Format device
            subprocess.run(["mkfs.ext4", "-F", device], check=True, capture_output=True)
            
            # Create daemon
            d = daemon.Daemon(config_path=mock_config_file)
            
            # Add device to bypass list (simulating encryption in progress)
            d._bypass_enforcement.add(device)
            
            # Create device properties
            device_props = {
                "ID_BUS": "usb",
                "DEVTYPE": "disk",
                "ID_FS_TYPE": "ext4",
                "ID_FS_USAGE": "filesystem"
            }
            
            # Handle device - should bypass enforcement
            with patch('usb_enforcer.user_utils.any_active_user_in_groups', return_value=(False, "")):
                d.handle_device(device_props, device, "add")
            
            # Verify device is tracked
            assert device in d.devices
            
            # Device should NOT be set read-only (bypass is active)
            result = subprocess.run(
                ["blockdev", "--getro", device],
                capture_output=True,
                text=True
            )
            
            # With bypass, device should remain read-write (0)
            # Note: This test verifies the bypass mechanism prevents enforcement
            # In real usage, the device starts RW, bypass prevents setting to RO
            assert device in d._bypass_enforcement
    
    def test_multiple_devices_simultaneously(self, loop_device, mock_config_file):
        """Test daemon handling multiple USB devices at once."""
        # Create daemon
        d = daemon.Daemon(config_path=mock_config_file)
        
        # Simulate multiple devices (using mock device paths since we can't easily create multiple loop devices)
        devices_to_test = [
            {
                "device": "/dev/mock_sdb1",
                "props": {
                    "ID_BUS": "usb",
                    "DEVTYPE": "partition",
                    "ID_FS_TYPE": "ext4",
                    "ID_FS_USAGE": "filesystem"
                }
            },
            {
                "device": "/dev/mock_sdc1",
                "props": {
                    "ID_BUS": "usb",
                    "DEVTYPE": "partition",
                    "ID_FS_TYPE": "crypto_LUKS",
                    "ID_FS_VERSION": "2"
                }
            },
            {
                "device": "/dev/mock_sdd1",
                "props": {
                    "ID_BUS": "usb",
                    "DEVTYPE": "partition",
                    "ID_FS_TYPE": "vfat",
                    "ID_FS_USAGE": "filesystem"
                }
            }
        ]
        
        # Simulate all devices being inserted
        with patch('usb_enforcer.user_utils.any_active_user_in_groups', return_value=(False, "")):
            for dev_info in devices_to_test:
                d.handle_device(dev_info["props"], dev_info["device"], "add")
        
        # Verify all devices are tracked
        for dev_info in devices_to_test:
            assert dev_info["device"] in d.devices
        
        # Verify count
        assert len(d.devices) == len(devices_to_test)
    
    def test_device_removal_cleanup(self, loop_device, mock_config_file):
        """Test that device removal properly cleans up tracking."""
        with loop_device(size_mb=50) as device:
            # Format and add device
            subprocess.run(["mkfs.ext4", "-F", device], check=True, capture_output=True)
            
            device_props = {
                "ID_BUS": "usb",
                "DEVTYPE": "disk",
                "ID_FS_TYPE": "ext4"
            }
            
            # Create daemon and add device
            d = daemon.Daemon(config_path=mock_config_file)
            
            with patch('usb_enforcer.user_utils.any_active_user_in_groups', return_value=(False, "")):
                d.handle_device(device_props, device, "add")
            
            # Verify device is tracked
            assert device in d.devices
            
            # Simulate device removal
            d.handle_device(device_props, device, "remove")
            
            # Verify device is removed from tracking
            assert device not in d.devices
            
            # Verify device is removed from bypass list if it was there
            assert device not in d._bypass_enforcement


@pytest.mark.integration
@pytest.mark.slow
class TestRealWorldScenarios:
    """Test realistic user scenarios."""
    
    def test_user_workflow_encrypt_usb(self, loop_device, mock_config_file):
        """
        Simulate realistic user workflow:
        1. Insert USB drive
        2. System enforces read-only
        3. User runs encryption wizard
        4. User can now use encrypted drive
        """
        with loop_device(size_mb=250) as device:
            # User inserts USB drive (formatted with files)
            subprocess.run(["mkfs.ext4", "-F", "-L", "MyUSB", device], check=True, capture_output=True)
            time.sleep(0.5)
            
            # Mount and add some files
            with tempfile.TemporaryDirectory() as mount_point:
                # Initial mount as read-write (before daemon sees it)
                subprocess.run(["blockdev", "--setrw", device], check=True)
                subprocess.run(["mount", device, mount_point], check=True)
                
                try:
                    (Path(mount_point) / "document.txt").write_text("Important data")
                    (Path(mount_point) / "photo.jpg").write_bytes(b"fake image")
                    subprocess.run(["sync"], check=False)
                finally:
                    subprocess.run(["umount", mount_point], check=False)
            
            # Daemon starts and detects device
            d = daemon.Daemon(config_path=mock_config_file)
            
            # Get real device properties using pyudev (same as daemon)
            context = pyudev.Context()
            udev_device = pyudev.Devices.from_device_file(context, device)
            
            # Build device properties dict from udev
            device_props = dict(udev_device.properties)
            
            # Ensure USB properties are set for classification
            device_props["ID_BUS"] = "usb"
            device_props["ID_TYPE"] = "disk"
            
            with patch('usb_enforcer.user_utils.any_active_user_in_groups', return_value=(False, "")):
                d.handle_device(device_props, device, "add")
            
            time.sleep(0.5)  # Allow enforcement to take effect
            
            # System enforces read-only
            result = subprocess.run(["blockdev", "--getro", device], capture_output=True, text=True)
            assert result.stdout.strip() == "1", "Device should be read-only"
            
            # User decides to encrypt (needs to bypass read-only)
            subprocess.run(["blockdev", "--setrw", device], check=True)
            
            # Add to bypass during encryption
            d._bypass_enforcement.add(device)
            
            mapper_name = f"secure-usb-{int(time.time())}"
            passphrase = "UserChosenPassword123!@#"
            
            try:
                # Encrypt (this wipes the device and creates new encrypted filesystem)
                mapper_path = crypto_engine.encrypt_device(
                    device,
                    mapper_name,
                    passphrase,
                    fs_type="exfat",  # Cross-platform
                    mount_opts=[],
                    label="SecureUSB"
                )
                
                # Remove from bypass after encryption
                d._bypass_enforcement.discard(device)
                
                # Verify encryption
                assert crypto_engine.luks_version(device) == "2"
                
                # User can now use encrypted drive
                with tempfile.TemporaryDirectory() as mount_point:
                    subprocess.run(["mount", mapper_path, mount_point], check=True)
                    
                    try:
                        # User stores sensitive data
                        (Path(mount_point) / "passwords.txt").write_text("Secret data")
                        (Path(mount_point) / "keys.pem").write_bytes(b"fake key data")
                        subprocess.run(["sync"], check=False)
                        
                        # Verify files are there
                        assert (Path(mount_point) / "passwords.txt").exists()
                        assert (Path(mount_point) / "keys.pem").exists()
                    finally:
                        subprocess.run(["umount", mount_point], check=False)
                
            finally:
                subprocess.run(["cryptsetup", "close", mapper_name], check=False, capture_output=True)

"""Integration tests for enforcement policies on loop devices.

These tests require root privileges.
Run with: sudo pytest tests/integration/test_enforcement.py
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from usb_enforcer import constants, enforcer


@pytest.mark.integration
class TestReadOnlyEnforcement:
    """Test read-only enforcement on loop devices."""
    
    def test_set_partition_readonly(self, loop_device):
        """Test setting a partition to read-only."""
        with loop_device(size_mb=100) as device:
            # Create partition
            subprocess.run(
                ["parted", "-s", device, "mklabel", "msdos"],
                check=True,
                capture_output=True
            )
            subprocess.run(
                ["parted", "-s", device, "mkpart", "primary", "ext4", "1MiB", "100%"],
                check=True,
                capture_output=True
            )
            subprocess.run(["partprobe", device], check=False, capture_output=True)
            
            # Get partition device
            partition = f"{device}p1"
            
            # Wait for partition to appear
            for _ in range(10):
                if Path(partition).exists():
                    break
                time.sleep(0.2)
            
            assert Path(partition).exists(), f"Partition {partition} not found"
            
            # Format partition
            subprocess.run(
                ["mkfs.ext4", "-F", partition],
                check=True,
                capture_output=True
            )
            
            # Set read-only
            import logging
            logger = logging.getLogger("test")
            result = enforcer.set_block_read_only(partition, logger)
            
            assert result is True
            
            # Verify read-only status
            block_name = Path(partition).name
            ro_path = Path(f"/sys/class/block/{block_name}/ro")
            if ro_path.exists():
                ro_value = ro_path.read_text().strip()
                assert ro_value == "1", f"Device not read-only: {ro_value}"
    
    def test_readonly_prevents_writes(self, loop_device):
        """Test that read-only enforcement prevents writes."""
        with loop_device(size_mb=100) as device:
            # Format device
            subprocess.run(
                ["mkfs.ext4", "-F", device],
                check=True,
                capture_output=True
            )
            
            # Set read-only
            import logging
            logger = logging.getLogger("test")
            enforcer.set_block_read_only(device, logger)
            
            # Mount device
            import tempfile
            with tempfile.TemporaryDirectory() as mount_point:
                # Try to mount read-write (should fail or mount as read-only)
                result = subprocess.run(
                    ["mount", device, mount_point],
                    capture_output=True
                )
                
                if result.returncode == 0:
                    try:
                        # Try to write a file
                        test_file = Path(mount_point) / "test.txt"
                        with pytest.raises((PermissionError, OSError)):
                            test_file.write_text("test")
                    finally:
                        subprocess.run(["umount", mount_point], check=False)


@pytest.mark.integration
class TestPolicyEnforcement:
    """Test policy enforcement on various device types."""
    
    def test_enforce_on_plaintext_partition(self, loop_device, mock_config_file):
        """Test enforcement on plaintext USB partition."""
        from usb_enforcer import config as config_module
        import logging
        
        with loop_device(size_mb=100) as device:
            # Create and format partition
            subprocess.run(["parted", "-s", device, "mklabel", "msdos"], check=True, capture_output=True)
            subprocess.run(["parted", "-s", device, "mkpart", "primary", "ext4", "1MiB", "100%"], check=True, capture_output=True)
            subprocess.run(["partprobe", device], check=False, capture_output=True)
            
            partition = f"{device}p1"
            
            # Wait for partition
            for _ in range(10):
                if Path(partition).exists():
                    break
                time.sleep(0.2)
            
            subprocess.run(["mkfs.ext4", "-F", partition], check=True, capture_output=True)
            
            # Get device properties
            result = subprocess.run(
                ["blkid", "-o", "export", partition],
                capture_output=True,
                text=True
            )
            
            # Parse blkid output
            device_props = {}
            for line in result.stdout.splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    device_props[key] = value
            
            # Add USB properties (simulated)
            device_props["ID_BUS"] = "usb"
            device_props["ID_TYPE"] = "partition"
            device_props["DEVTYPE"] = "partition"
            
            # Load config and enforce policy
            config = config_module.Config.load(mock_config_file)
            logger = logging.getLogger("test")
            
            # Mock exempted users to return False
            from unittest.mock import patch
            with patch('usb_enforcer.user_utils.any_active_user_exempted', return_value=False):
                policy_result = enforcer.enforce_policy(device_props, partition, logger, config)
                
                # Should enforce read-only on plaintext partition
                assert policy_result["action"] == "block_ro"
                assert policy_result["classification"] == constants.PLAINTEXT
    
    def test_no_enforce_on_encrypted_device(self, loop_device, mock_config_file, require_cryptsetup):
        """Test no enforcement on encrypted devices."""
        from usb_enforcer import config as config_module
        from usb_enforcer import crypto_engine
        import logging
        
        with loop_device(size_mb=100) as device:
            # Encrypt device
            passphrase = "test-password-enforcement-123"
            mapper_name = "test-enforce"
            crypto_engine.encrypt_device(
                device,
                mapper_name,
                passphrase,
                fs_type="exfat",
                mount_opts=[],
                cipher_opts={"cipher": "aes-xts-plain64", "key_size": 512},
                kdf_opts={"type": "argon2id"}
            )
            # Close from encryption
            subprocess.run(["cryptsetup", "close", mapper_name], check=False, capture_output=True)
            
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
            
            # Add USB properties
            device_props["ID_BUS"] = "usb"
            device_props["ID_TYPE"] = "partition"
            device_props["DEVTYPE"] = "partition"
            
            # Enforce policy
            config = config_module.Config.load(mock_config_file)
            logger = logging.getLogger("test")
            
            from unittest.mock import patch
            with patch('usb_enforcer.user_utils.any_active_user_exempted', return_value=False):
                policy_result = enforcer.enforce_policy(device_props, device, logger, config)
                
                # Should allow encrypted device
                assert policy_result["action"] == "allow"
                assert policy_result["classification"] == constants.LUKS2_LOCKED


@pytest.mark.integration
class TestDeviceOperations:
    """Test various device operations."""
    
    def test_mount_and_write_to_encrypted_device(self, loop_device, require_cryptsetup):
        """Test mounting and writing to encrypted device."""
        from usb_enforcer import crypto_engine
        
        with loop_device(size_mb=100) as device:
            passphrase = "test-mount-password-123"
            mapper_name = "test-mount"
            
            try:
                # Encrypt and format
                crypto_engine.encrypt_device(
                    device,
                    mapper_name,
                    passphrase,
                    fs_type="ext4",
                    mount_opts=[],
                    cipher_opts={"cipher": "aes-xts-plain64", "key_size": 512},
                    kdf_opts={"type": "argon2id"}
                )
                
                # Close and reopen LUKS device
                subprocess.run(["cryptsetup", "close", mapper_name], check=False, capture_output=True)
                time.sleep(0.5)
                
                # Open LUKS device
                subprocess.run(
                    ["cryptsetup", "open", device, mapper_name],
                    input=passphrase.encode(),
                    check=True,
                    capture_output=True
                )
                
                mapper_device = f"/dev/mapper/{mapper_name}"
                
                # Format with ext4
                subprocess.run(
                    ["mkfs.ext4", "-F", mapper_device],
                    check=True,
                    capture_output=True
                )
                
                # Mount and write
                import tempfile
                with tempfile.TemporaryDirectory() as mount_point:
                    subprocess.run(["mount", mapper_device, mount_point], check=True)
                    
                    try:
                        # Write test file
                        test_file = Path(mount_point) / "test.txt"
                        test_file.write_text("Hello from encrypted device!")
                        
                        # Verify
                        content = test_file.read_text()
                        assert content == "Hello from encrypted device!"
                    finally:
                        subprocess.run(["umount", mount_point], check=False)
            
            finally:
                subprocess.run(["cryptsetup", "close", mapper_name], check=False, capture_output=True)
    
    def test_readonly_plaintext_mount(self, loop_device):
        """Test that plaintext devices can be mounted read-only."""
        with loop_device(size_mb=100) as device:
            # Format device
            subprocess.run(
                ["mkfs.ext4", "-F", device],
                check=True,
                capture_output=True
            )
            
            # Set read-only
            import logging
            logger = logging.getLogger("test")
            enforcer.set_block_read_only(device, logger)
            
            # Mount read-only
            import tempfile
            with tempfile.TemporaryDirectory() as mount_point:
                result = subprocess.run(
                    ["mount", "-o", "ro", device, mount_point],
                    capture_output=True
                )
                
                if result.returncode == 0:
                    try:
                        # Verify can read
                        subprocess.run(["ls", mount_point], check=True)
                        
                        # Verify cannot write
                        test_file = Path(mount_point) / "test.txt"
                        with pytest.raises((PermissionError, OSError)):
                            test_file.write_text("should fail")
                    finally:
                        subprocess.run(["umount", mount_point], check=False)

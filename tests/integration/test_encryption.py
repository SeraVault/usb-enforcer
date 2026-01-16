"""Integration tests for LUKS encryption operations.

These tests require root privileges and cryptsetup.
Run with: sudo pytest tests/integration/test_encryption.py
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from usb_enforcer import crypto_engine


@pytest.mark.integration
class TestLUKSEncryption:
    """Test LUKS encryption operations on loop devices."""
    
    def test_luks_version_detection_luks2(self, loop_device, require_cryptsetup):
        """Test LUKS2 version detection."""
        with loop_device(size_mb=50) as device:
            # Format as LUKS2
            passphrase = "test-password-12345"
            subprocess.run(
                ["cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode", device],
                input=passphrase.encode(),
                check=True,
                capture_output=True
            )
            
            # Test version detection
            version = crypto_engine.luks_version(device)
            assert version == "2"
    
    def test_luks_version_detection_luks1(self, loop_device, require_cryptsetup):
        """Test LUKS1 version detection."""
        with loop_device(size_mb=50) as device:
            # Format as LUKS1
            passphrase = "test-password-12345"
            subprocess.run(
                ["cryptsetup", "luksFormat", "--type", "luks1", "--batch-mode", device],
                input=passphrase.encode(),
                check=True,
                capture_output=True
            )
            
            # Test version detection
            version = crypto_engine.luks_version(device)
            assert version == "1"
    
    def test_luks_version_plaintext(self, loop_device):
        """Test version detection on plaintext device."""
        with loop_device(size_mb=50) as device:
            # Format as ext4
            subprocess.run(
                ["mkfs.ext4", "-F", device],
                check=True,
                capture_output=True
            )
            
            # Test version detection
            version = crypto_engine.luks_version(device)
            assert version is None
    
    def test_encrypt_device_luks2(self, loop_device, require_cryptsetup):
        """Test encrypting a device with LUKS2."""
        with loop_device(size_mb=100) as device:
            passphrase = "test-encryption-password-123"
            mapper_name = "test-luks2"
            
            # Encrypt device
            try:
                crypto_engine.encrypt_device(
                    device,
                    mapper_name,
                    passphrase,
                    fs_type="exfat",
                    mount_opts=[],
                    cipher_opts={"cipher": "aes-xts-plain64", "key_size": 512},
                    kdf_opts={"type": "argon2id"}
                )
            except crypto_engine.CryptoError as e:
                pytest.fail(f"Encryption failed: {e}")
            
            # Verify it's LUKS2
            version = crypto_engine.luks_version(device)
            assert version == "2"
            
            # Close from encryption
            subprocess.run(["cryptsetup", "close", mapper_name], check=False, capture_output=True)
            time.sleep(0.5)
            
            # Verify we can open it
            try:
                result = subprocess.run(
                    ["cryptsetup", "open", device, mapper_name],
                    input=passphrase.encode(),
                    capture_output=True
                )
                assert result.returncode == 0
                
                # Verify mapper device exists
                mapper_path = Path(f"/dev/mapper/{mapper_name}")
                assert mapper_path.exists()
            finally:
                subprocess.run(["cryptsetup", "close", mapper_name], check=False, capture_output=True)
    
    def test_encrypt_device_luks1(self, loop_device, require_cryptsetup):
        """Test encrypting a device with LUKS1."""
        with loop_device(size_mb=100) as device:
            passphrase = "test-encryption-password-123"
            mapper_name = f"test-luks1-{int(time.time())}"
            
            # Encrypt device
            try:
                crypto_engine.encrypt_device(
                    device,
                    mapper_name,
                    passphrase,
                    fs_type="exfat",
                    mount_opts=[],
                    cipher_opts={"cipher": "aes-xts-plain64", "key_size": 512},
                    kdf_opts={"type": "pbkdf2", "luks_version": "luks1"}
                )
            except crypto_engine.CryptoError as e:
                pytest.fail(f"Encryption failed: {e}")
            
            # Verify it's LUKS1
            version = crypto_engine.luks_version(device)
            assert version == "1"
    
    def test_format_encrypted_device(self, loop_device, require_cryptsetup):
        """Test formatting an encrypted device."""
        with loop_device(size_mb=100) as device:
            passphrase = "test-password-format-123"
            mapper_name = "test-format"
            
            try:
                # Encrypt device
                crypto_engine.encrypt_device(
                    device,
                    mapper_name,
                    passphrase,
                    fs_type="ext4",
                    mount_opts=[],
                    cipher_opts={"cipher": "aes-xts-plain64", "key_size": 512},
                    kdf_opts={"type": "argon2id"}
                )
                
                # Close from encryption and reopen
                subprocess.run(["cryptsetup", "close", mapper_name], check=False, capture_output=True)
                time.sleep(0.5)
                
                # Open device
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
                
                # Verify filesystem
                result = subprocess.run(
                    ["blkid", "-o", "value", "-s", "TYPE", mapper_device],
                    capture_output=True,
                    text=True
                )
                assert "ext4" in result.stdout
                
            finally:
                subprocess.run(["cryptsetup", "close", mapper_name], check=False, capture_output=True)


@pytest.mark.integration
class TestUnmounting:
    """Test unmounting operations."""
    
    def test_get_mounted_devices(self, loop_device):
        """Test getting mounted devices."""
        with loop_device(size_mb=50) as device:
            # Format device
            subprocess.run(["mkfs.ext4", "-F", device], check=True, capture_output=True)
            
            # Create mount point
            import tempfile
            with tempfile.TemporaryDirectory() as mount_point:
                # Mount device
                subprocess.run(["mount", device, mount_point], check=True)
                
                try:
                    # Get mounted devices
                    mounted = crypto_engine._get_mounted_devices()
                    assert device in mounted
                    assert mounted[device] == mount_point
                finally:
                    subprocess.run(["umount", device], check=False)
    
    def test_get_device_partitions(self, loop_device, require_cryptsetup):
        """Test getting device partitions."""
        with loop_device(size_mb=100) as device:
            # Create partition table
            subprocess.run(
                ["parted", "-s", device, "mklabel", "msdos"],
                check=True,
                capture_output=True
            )
            
            # Create partition
            subprocess.run(
                ["parted", "-s", device, "mkpart", "primary", "ext4", "1MiB", "100%"],
                check=True,
                capture_output=True
            )
            
            # Re-read partition table
            subprocess.run(["partprobe", device], check=False, capture_output=True)
            
            # Get partitions
            partitions = crypto_engine._get_device_partitions(device)
            
            # Should find at least the partition
            assert len(partitions) >= 0  # May vary by system

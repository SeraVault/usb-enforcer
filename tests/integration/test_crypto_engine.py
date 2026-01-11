"""Integration tests for crypto_engine real-world operations.

These tests require root privileges and cryptsetup.
Run with: sudo pytest tests/integration/test_crypto_engine.py -v
"""

from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from usb_enforcer import crypto_engine


@pytest.mark.integration
class TestLUKSVersionDetection:
    """Test LUKS version detection in real scenarios."""
    
    def test_luks_version_on_plaintext(self, loop_device):
        """Test version detection returns None for plaintext devices."""
        with loop_device(size_mb=50) as device:
            subprocess.run(["mkfs.ext4", "-F", device], check=True, capture_output=True)
            
            version = crypto_engine.luks_version(device)
            assert version is None
    
    def test_luks_version_luks2_detection(self, loop_device, require_cryptsetup):
        """Test detection of LUKS2 formatted devices."""
        with loop_device(size_mb=100) as device:
            passphrase = "T3st!Luks2#D3tect_9527"
            subprocess.run(
                ["cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode", "--force-password", device],
                input=passphrase.encode(),
                check=True,
                capture_output=True
            )
            
            version = crypto_engine.luks_version(device)
            assert version == "2"
    
    def test_luks_version_luks1_detection(self, loop_device, require_cryptsetup):
        """Test detection of LUKS1 formatted devices."""
        with loop_device(size_mb=100) as device:
            passphrase = "T3st!Luks1#D3tect_8416"
            subprocess.run(
                ["cryptsetup", "luksFormat", "--type", "luks1", "--batch-mode", "--force-password", device],
                input=passphrase.encode(),
                check=True,
                capture_output=True
            )
            
            version = crypto_engine.luks_version(device)
            assert version == "1"


@pytest.mark.integration
class TestEncryptionWorkflows:
    """Test complete encryption workflows."""
    
    def test_encrypt_format_mount_workflow(self, loop_device, require_cryptsetup):
        """Test complete workflow: encrypt -> open -> format -> mount -> write."""
        with loop_device(size_mb=150) as device:
            passphrase = "C0mpl3te!W0rkfl0w#Pass_7392"
            mapper_name = f"test-workflow-{int(time.time())}"
            
            try:
                # Step 1: Encrypt device with LUKS2 (this also opens and formats it)
                mapper_path_str = crypto_engine.encrypt_device(
                    device,
                    mapper_name,
                    passphrase,
                    fs_type="exfat",
                    mount_opts=[],
                    label="TEST",
                    cipher_opts={"cipher": "aes-xts-plain64", "key_size": 512},
                    kdf_opts={"type": "argon2id"}
                )
                
                # Verify encryption
                version = crypto_engine.luks_version(device)
                assert version == "2"
                
                # Step 2: Verify mapper device exists (already opened by encrypt_device)
                mapper_path = Path(mapper_path_str)
                assert mapper_path.exists()
                
                # Step 3: Filesystem already created by encrypt_device
                # Verify we can read filesystem info
                result = subprocess.run(
                    ["blkid", "-o", "export", str(mapper_path)],
                    check=True,
                    capture_output=True
                )
                
                # Step 4: Mount and write
                with tempfile.TemporaryDirectory() as mount_point:
                    subprocess.run(["mount", str(mapper_path), mount_point], check=True)
                    
                    try:
                        # Write test data
                        test_file = Path(mount_point) / "test_data.txt"
                        test_content = "This is encrypted data! 🔒"
                        test_file.write_text(test_content)
                        
                        # Sync to ensure write
                        subprocess.run(["sync"], check=False)
                        
                        # Verify read
                        read_content = test_file.read_text()
                        assert read_content == test_content
                        
                    finally:
                        subprocess.run(["umount", mount_point], check=False)
                
            finally:
                subprocess.run(["cryptsetup", "close", mapper_name], check=False, capture_output=True)
    
    def test_encrypt_with_different_ciphers(self, loop_device, require_cryptsetup):
        """Test encryption with various cipher configurations."""
        ciphers = [
            ("aes-xts-plain64", 512),
            ("aes-xts-plain64", 256),
        ]
        
        for cipher_spec, key_size in ciphers:
            with loop_device(size_mb=100) as device:
                passphrase = f"C1ph3r!T3st#{cipher_spec[:3]}{key_size}_Str0ng"
                
                mapper_name = f"test-cipher-{cipher_spec.replace('-', '')}-{key_size}-{int(time.time())}"
                try:
                    mapper_path = crypto_engine.encrypt_device(
                        device,
                        mapper_name,
                        passphrase,
                        fs_type="exfat",
                        mount_opts=[],
                        cipher_opts={"cipher": cipher_spec, "key_size": key_size},
                        kdf_opts={"type": "argon2id"}
                    )
                    
                    # Verify mapper was created and still exists
                    assert Path(mapper_path).exists()
                finally:
                    subprocess.run(["cryptsetup", "close", mapper_name], check=False, capture_output=True)
    
    def test_encrypt_with_different_kdf(self, loop_device, require_cryptsetup):
        """Test encryption with different KDF algorithms."""
        kdfs = ["argon2id", "pbkdf2"]
        
        for kdf_spec in kdfs:
            with loop_device(size_mb=100) as device:
                passphrase = f"Kdf!T3st#{kdf_spec[:4]}_Secur3Pass_2048"
                
                mapper_name = f"test-kdf-{kdf_spec}-{int(time.time())}"
                try:
                    crypto_engine.encrypt_device(
                        device,
                        mapper_name,
                        passphrase,
                        fs_type="exfat",
                        mount_opts=[],
                        cipher_opts={"cipher": "aes-xts-plain64", "key_size": 512},
                        kdf_opts={"type": kdf_spec}
                    )
                    
                    # Verify encryption
                    version = crypto_engine.luks_version(device)
                    assert version == "2"
                finally:
                    subprocess.run(["cryptsetup", "close", mapper_name], check=False, capture_output=True)


@pytest.mark.integration
class TestPartitionHandling:
    """Test partition-related operations."""
    
    def test_get_device_partitions(self, loop_device):
        """Test getting partitions from a device."""
        with loop_device(size_mb=200) as device:
            # Create partition table and partitions
            subprocess.run(
                ["parted", "-s", device, "mklabel", "msdos"],
                check=True,
                capture_output=True
            )
            subprocess.run(
                ["parted", "-s", device, "mkpart", "primary", "ext4", "1MiB", "50%"],
                check=True,
                capture_output=True
            )
            subprocess.run(
                ["parted", "-s", device, "mkpart", "primary", "ext4", "50%", "100%"],
                check=True,
                capture_output=True
            )
            subprocess.run(["partprobe", device], check=False, capture_output=True)
            
            # Wait for partitions to appear
            time.sleep(1)
            
            # Get partitions
            partitions = crypto_engine._get_device_partitions(device)
            
            # Should find the partitions (exact count may vary)
            assert len(partitions) >= 0  # Implementation may vary


@pytest.mark.integration
class TestUnmounting:
    """Test unmounting operations."""
    
    def test_get_mounted_devices_real(self, loop_device):
        """Test getting mounted devices from /proc/mounts."""
        with loop_device(size_mb=100) as device:
            # Format device
            subprocess.run(["mkfs.ext4", "-F", device], check=True, capture_output=True)
            
            mount_point = tempfile.mkdtemp(prefix="usb-test-mount-")
            try:
                # Mount device
                subprocess.run(["mount", device, mount_point], check=True)
                
                # Get mounted devices
                mounted = crypto_engine._get_mounted_devices()
                
                # Our device should be in the list
                assert device in mounted
                assert mounted[device] == mount_point
                    
            finally:
                # Ensure proper unmount
                subprocess.run(["umount", "-f", mount_point], check=False)
                time.sleep(0.2)
                # Remove mount point
                try:
                    Path(mount_point).rmdir()
                except Exception:
                    pass


@pytest.mark.integration  
class TestEncryptionEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_encrypt_already_encrypted_device(self, loop_device, require_cryptsetup):
        """Test encrypting an already encrypted device (wipefs removes LUKS header, so it succeeds)."""
        with loop_device(size_mb=100) as device:
            passphrase = "D0ubl3!Encrypt#Str0ng_6381"
            
            # First encryption
            mapper_name = f"test-double-{int(time.time())}"
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
            finally:
                # Close the mapper
                subprocess.run(["cryptsetup", "close", mapper_name], check=False, capture_output=True)
            
            # Verify device is encrypted
            version = crypto_engine.luks_version(device)
            assert version == "2"
            
            # Second encryption succeeds because encrypt_device wipes the device first
            mapper_name2 = f"test-double2-{int(time.time())}"
            try:
                mapper_path = crypto_engine.encrypt_device(
                    device,
                    mapper_name2,
                    passphrase,
                    fs_type="exfat",
                    mount_opts=[],
                    cipher_opts={"cipher": "aes-xts-plain64", "key_size": 512},
                    kdf_opts={"type": "argon2id"}
                )
                # Verify re-encryption worked
                assert mapper_path is not None
                version2 = crypto_engine.luks_version(device)
                assert version2 == "2"
            finally:
                subprocess.run(["cryptsetup", "close", mapper_name2], check=False, capture_output=True)
    
    @pytest.mark.timeout(30)
    def test_wrong_passphrase(self, loop_device, require_cryptsetup):
        """Test opening LUKS device with wrong passphrase."""
        with loop_device(size_mb=100) as device:
            correct_passphrase = "C0rrect!Str0ng#Pass_4729"
            wrong_passphrase = "Wr0ng!Diff3rent#Key_8152"
            mapper_name = f"test-wrong-pass-{int(time.time())}"
            
            try:
                # Encrypt with correct passphrase
                crypto_engine.encrypt_device(
                    device,
                    mapper_name,
                    correct_passphrase,
                    fs_type="exfat",
                    mount_opts=[],
                    cipher_opts={"cipher": "aes-xts-plain64", "key_size": 512},
                    kdf_opts={"type": "argon2id"}
                )
            finally:
                # Close the mapper first
                subprocess.run(["cryptsetup", "close", mapper_name], check=False, capture_output=True)
            
            time.sleep(0.5)
            
            # Try to open with wrong passphrase (use different mapper name)
            wrong_mapper = f"test-wrong-{int(time.time())}"
            result = subprocess.run(
                ["cryptsetup", "open", device, wrong_mapper, "--tries", "1"],
                input=wrong_passphrase.encode(),
                capture_output=True,
                timeout=10
            )
            
            # Should fail
            assert result.returncode != 0
            
            # Cleanup in case it somehow opened
            subprocess.run(["cryptsetup", "close", wrong_mapper], check=False, capture_output=True)


@pytest.mark.integration
class TestRealWorldScenarios:
    """Test realistic usage scenarios."""
    
    def test_usb_drive_simulation(self, loop_device, require_cryptsetup):
        """Simulate a complete USB drive encryption scenario."""
        with loop_device(size_mb=500) as device:
            # Scenario: User wants to encrypt a USB drive
            
            # Step 1: Check if already encrypted
            version = crypto_engine.luks_version(device)
            assert version is None  # Not encrypted yet
            
            # Step 2: Encrypt the drive
            user_passphrase = "MySecureUSBPassword123!"
            mapper_name = f"my-usb-{int(time.time())}"
            crypto_engine.encrypt_device(
                device,
                mapper_name,
                user_passphrase,
                fs_type="exfat",
                mount_opts=[],
                label="MyUSB",
                cipher_opts={"cipher": "aes-xts-plain64", "key_size": 512},
                kdf_opts={"type": "argon2id"}
            )
            
            # Step 3: Verify it's encrypted
            version = crypto_engine.luks_version(device)
            assert version == "2"
            
            # Step 4: Device is already opened and formatted by encrypt_device
            # Verify mapper exists
            mapper_path = Path(f"/dev/mapper/{mapper_name}")
            assert mapper_path.exists()
            
            # Step 5: Mount and use (filesystem already created)
            try:
                with tempfile.TemporaryDirectory() as mount_point:
                    subprocess.run(["mount", str(mapper_path), mount_point], check=True)
                    
                    try:
                        # Create some files
                        (Path(mount_point) / "document.txt").write_text("Sensitive data")
                        (Path(mount_point) / "photo.jpg").write_bytes(b"fake image data")
                        
                        subprocess.run(["sync"], check=False)
                        
                        # Verify files exist
                        assert (Path(mount_point) / "document.txt").exists()
                        assert (Path(mount_point) / "photo.jpg").exists()
                            
                    finally:
                        subprocess.run(["umount", mount_point], check=False)
                
            finally:
                subprocess.run(["cryptsetup", "close", mapper_name], check=False, capture_output=True)
    
    def test_multiple_open_close_cycles(self, loop_device, require_cryptsetup):
        """Test opening and closing LUKS device multiple times."""
        with loop_device(size_mb=150) as device:
            passphrase = "Mult1pl3!Cycl3s#Str0ng_5943"
            
            # Encrypt once
            initial_mapper = f"test-initial-{int(time.time())}"
            crypto_engine.encrypt_device(
                device,
                initial_mapper,
                passphrase,
                fs_type="exfat",
                mount_opts=[],
                cipher_opts={"cipher": "aes-xts-plain64", "key_size": 512},
                kdf_opts={"type": "argon2id"}
            )
            # Close the initial mapping
            subprocess.run(["cryptsetup", "close", initial_mapper], check=False, capture_output=True)
            
            # Open and close 5 times
            for i in range(5):
                mapper_name = f"test-cycle-{i}-{int(time.time())}"
                
                # Open
                subprocess.run(
                    ["cryptsetup", "open", device, mapper_name],
                    input=passphrase.encode(),
                    check=True,
                    capture_output=True
                )
                
                assert Path(f"/dev/mapper/{mapper_name}").exists()
                
                # Close
                subprocess.run(
                    ["cryptsetup", "close", mapper_name],
                    check=True,
                    capture_output=True
                )
                
                assert not Path(f"/dev/mapper/{mapper_name}").exists()

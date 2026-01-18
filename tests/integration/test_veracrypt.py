"""Integration tests for VeraCrypt encryption operations.

These tests require root privileges and veracrypt.
Run with: sudo pytest tests/integration/test_veracrypt.py
"""

from __future__ import annotations

import glob
import os
import subprocess
import time
from pathlib import Path

import pytest

from usb_enforcer import crypto_engine


@pytest.mark.integration
class TestVeraCryptEncryption:
    """Test VeraCrypt encryption operations on loop devices."""
    
    def test_veracrypt_version_detection(self, loop_device, require_veracrypt):
        """Test VeraCrypt volume detection."""
        with loop_device(size_mb=100) as device:
            passphrase = "test-veracrypt-pass-12345"
            
            # Create VeraCrypt volume
            create_cmd = [
                "veracrypt",
                "--text",
                "--create",
                device,
                "--volume-type=normal",
                "--encryption=AES",
                "--hash=SHA-512",
                "--filesystem=none",
                "--stdin",
                "--pim=0",
                "--keyfiles=",
                "--random-source=/dev/urandom",
                "--non-interactive"
            ]
            subprocess.run(
                create_cmd,
                input=passphrase.encode(),
                check=True,
                capture_output=True
            )
            
            # Test version detection
            version = crypto_engine.veracrypt_version(device)
            assert version == "veracrypt"
    
    def test_veracrypt_version_plaintext(self, loop_device):
        """Test version detection on plaintext device."""
        with loop_device(size_mb=50) as device:
            # Format as ext4
            subprocess.run(
                ["mkfs.ext4", "-F", device],
                check=True,
                capture_output=True
            )
            
            # Test version detection - should not detect VeraCrypt
            version = crypto_engine.veracrypt_version(device)
            assert version is None
    
    def test_veracrypt_version_luks(self, loop_device, require_cryptsetup):
        """Test VeraCrypt detection doesn't false-positive on LUKS."""
        with loop_device(size_mb=50) as device:
            passphrase = "test-password-12345"
            subprocess.run(
                ["cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode", device],
                input=passphrase.encode(),
                check=True,
                capture_output=True
            )
            
            # Test version detection - should not detect VeraCrypt
            version = crypto_engine.veracrypt_version(device)
            assert version is None
    
    def test_encrypt_device_veracrypt(self, loop_device, require_veracrypt):
        """Test encrypting a device with VeraCrypt."""
        with loop_device(size_mb=150) as device:
            passphrase = "test-veracrypt-encryption-password-123"
            mapper_name = f"test-vc-{int(time.time())}"
            
            # Encrypt device with VeraCrypt
            try:
                result = crypto_engine.encrypt_device(
                    device,
                    mapper_name,
                    passphrase,
                    fs_type="exfat",
                    mount_opts=[],
                    encryption_type="veracrypt"
                )
                print(f"Encryption result: {result}")
            except crypto_engine.CryptoError as e:
                pytest.fail(f"VeraCrypt encryption failed: {e}")
            
            # Verify it's VeraCrypt
            version = crypto_engine.veracrypt_version(device)
            assert version == "veracrypt"
            
            # Cleanup - dismount if mounted
            try:
                subprocess.run(
                    ["veracrypt", "--text", "--dismount", device],
                    check=False,
                    capture_output=True
                )
            except Exception:
                pass
            
            # Clean up mount point if it exists
            username = os.environ.get('SUDO_USER') or os.environ.get('USER') or 'root'
            mount_point = f"/media/{username}/{mapper_name}"
            if os.path.exists(mount_point):
                try:
                    os.rmdir(mount_point)
                except Exception:
                    pass
    
    def test_unlock_veracrypt(self, loop_device, require_veracrypt):
        """Test unlocking a VeraCrypt encrypted device."""
        with loop_device(size_mb=150) as device:
            passphrase = "test-veracrypt-unlock-pass-456"
            mapper_name = f"test-vc-unlock-{int(time.time())}"
            
            # First create a VeraCrypt volume
            create_cmd = [
                "veracrypt",
                "--text",
                "--create",
                device,
                "--volume-type=normal",
                "--encryption=AES",
                "--hash=SHA-512",
                "--filesystem=none",
                "--stdin",
                "--pim=0",
                "--keyfiles=",
                "--random-source=/dev/urandom",
                "--non-interactive"
            ]
            subprocess.run(
                create_cmd,
                input=passphrase.encode(),
                check=True,
                capture_output=True
            )
            
            try:
                # Test unlocking
                result = crypto_engine.unlock_veracrypt(device, mapper_name, passphrase)
                print(f"Unlock result: {result}")
                
                # Verify mount point or mapper exists
                assert result is not None
                if result.startswith("/media/"):
                    assert os.path.exists(result)
                elif result.startswith("/dev/mapper/"):
                    assert os.path.exists(result)
                else:
                    pytest.fail(f"Unexpected result path: {result}")
            
            finally:
                # Cleanup
                try:
                    subprocess.run(
                        ["veracrypt", "--text", "--dismount", device],
                        check=False,
                        capture_output=True
                    )
                except Exception:
                    pass
                
                # Clean up mount point
                username = os.environ.get('SUDO_USER') or os.environ.get('USER') or 'root'
                mount_point = f"/media/{username}/{mapper_name}"
                if os.path.exists(mount_point):
                    try:
                        os.rmdir(mount_point)
                    except Exception:
                        pass
    
    def test_close_veracrypt_mapper(self, loop_device, require_veracrypt):
        """Test closing a VeraCrypt volume."""
        with loop_device(size_mb=150) as device:
            passphrase = "test-veracrypt-close-pass-789"
            mapper_name = f"test-vc-close-{int(time.time())}"
            
            # Create and mount VeraCrypt volume
            create_cmd = [
                "veracrypt",
                "--text",
                "--create",
                device,
                "--volume-type=normal",
                "--encryption=AES",
                "--hash=SHA-512",
                "--filesystem=none",
                "--stdin",
                "--pim=0",
                "--keyfiles=",
                "--random-source=/dev/urandom",
                "--non-interactive"
            ]
            subprocess.run(
                create_cmd,
                input=passphrase.encode(),
                check=True,
                capture_output=True
            )
            
            # Mount it
            username = os.environ.get('SUDO_USER') or os.environ.get('USER') or 'root'
            mount_point = f"/media/{username}/{mapper_name}"
            os.makedirs(os.path.dirname(mount_point), exist_ok=True)
            
            mount_cmd = [
                "veracrypt",
                "--text",
                "--non-interactive",
                "--stdin",
                device,
                mount_point
            ]
            subprocess.run(
                mount_cmd,
                input=passphrase.encode(),
                check=True,
                capture_output=True
            )
            
            # Give VeraCrypt time to create mapper
            time.sleep(1)
            
            # Verify mount exists
            assert os.path.ismount(mount_point) or len(glob.glob("/dev/mapper/veracrypt*")) > 0
            
            # Test closing
            try:
                crypto_engine.close_mapper(mapper_name, "veracrypt")
                
                # Verify it's closed
                time.sleep(0.5)
                if os.path.exists(mount_point):
                    assert not os.path.ismount(mount_point)
            
            finally:
                # Ensure cleanup
                try:
                    subprocess.run(
                        ["veracrypt", "--text", "--dismount", device],
                        check=False,
                        capture_output=True
                    )
                except Exception:
                    pass
                
                if os.path.exists(mount_point):
                    try:
                        os.rmdir(mount_point)
                    except Exception:
                        pass
    
    def test_format_veracrypt_device(self, loop_device, require_veracrypt):
        """Test formatting a VeraCrypt encrypted device with a filesystem."""
        with loop_device(size_mb=200) as device:
            passphrase = "test-veracrypt-format-pass-abc"
            mapper_name = f"test-vc-fmt-{int(time.time())}"
            
            try:
                # Encrypt with VeraCrypt and format with ext4
                result = crypto_engine.encrypt_device(
                    device,
                    mapper_name,
                    passphrase,
                    fs_type="ext4",
                    mount_opts=[],
                    encryption_type="veracrypt"
                )
                
                print(f"Formatted VeraCrypt device: {result}")
                
                # Find the actual mapper device
                mappers = glob.glob("/dev/mapper/veracrypt*")
                assert len(mappers) > 0, "No VeraCrypt mapper device found"
                
                mapper_device = sorted(mappers, key=lambda x: os.path.getmtime(x))[-1]
                
                # Verify filesystem exists
                result = subprocess.run(
                    ["blkid", "-o", "value", "-s", "TYPE", mapper_device],
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                if result.returncode == 0:
                    assert "ext4" in result.stdout.lower()
                
            finally:
                # Cleanup
                try:
                    subprocess.run(
                        ["veracrypt", "--text", "--dismount", device],
                        check=False,
                        capture_output=True
                    )
                except Exception:
                    pass
                
                username = os.environ.get('SUDO_USER') or os.environ.get('USER') or 'root'
                mount_point = f"/media/{username}/{mapper_name}"
                if os.path.exists(mount_point):
                    try:
                        os.rmdir(mount_point)
                    except Exception:
                        pass
    
    def test_veracrypt_with_label(self, loop_device, require_veracrypt):
        """Test VeraCrypt encryption with filesystem label."""
        with loop_device(size_mb=150) as device:
            passphrase = "test-veracrypt-label-pass-xyz"
            mapper_name = f"test-vc-lbl-{int(time.time())}"
            label = "TESTVC"
            
            try:
                # Encrypt with VeraCrypt and exfat with label
                result = crypto_engine.encrypt_device(
                    device,
                    mapper_name,
                    passphrase,
                    fs_type="exfat",
                    mount_opts=[],
                    label=label,
                    encryption_type="veracrypt"
                )
                
                print(f"Labeled VeraCrypt device: {result}")
                
                # Find mapper device
                mappers = glob.glob("/dev/mapper/veracrypt*")
                if mappers:
                    mapper_device = sorted(mappers, key=lambda x: os.path.getmtime(x))[-1]
                    
                    # Check label (note: label checking may vary by filesystem)
                    result = subprocess.run(
                        ["blkid", "-o", "value", "-s", "LABEL", mapper_device],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    
                    # exfat labels may be uppercase
                    if result.returncode == 0 and result.stdout.strip():
                        assert label.upper() in result.stdout.upper()
            
            finally:
                # Cleanup
                try:
                    subprocess.run(
                        ["veracrypt", "--text", "--dismount", device],
                        check=False,
                        capture_output=True
                    )
                except Exception:
                    pass
                
                username = os.environ.get('SUDO_USER') or os.environ.get('USER') or 'root'
                mount_point = f"/media/{username}/{mapper_name}"
                if os.path.exists(mount_point):
                    try:
                        os.rmdir(mount_point)
                    except Exception:
                        pass


@pytest.mark.integration
class TestVeraCryptInteroperability:
    """Test interoperability between LUKS and VeraCrypt detection."""
    
    def test_luks_not_detected_as_veracrypt(self, loop_device, require_cryptsetup, require_veracrypt):
        """Verify LUKS devices are not misidentified as VeraCrypt."""
        with loop_device(size_mb=100) as device:
            passphrase = "test-luks-pass-123"
            
            # Create LUKS2 volume
            subprocess.run(
                ["cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode", device],
                input=passphrase.encode(),
                check=True,
                capture_output=True
            )
            
            # Verify LUKS detection works
            luks_ver = crypto_engine.luks_version(device)
            assert luks_ver == "2"
            
            # Verify NOT detected as VeraCrypt
            vc_ver = crypto_engine.veracrypt_version(device)
            assert vc_ver is None
    
    def test_veracrypt_not_detected_as_luks(self, loop_device, require_cryptsetup, require_veracrypt):
        """Verify VeraCrypt volumes are not misidentified as LUKS."""
        with loop_device(size_mb=150) as device:
            passphrase = "test-vc-pass-456"
            
            # Create VeraCrypt volume
            create_cmd = [
                "veracrypt",
                "--text",
                "--create",
                device,
                "--volume-type=normal",
                "--encryption=AES",
                "--hash=SHA-512",
                "--filesystem=none",
                "--stdin",
                "--pim=0",
                "--keyfiles=",
                "--random-source=/dev/urandom",
                "--non-interactive"
            ]
            subprocess.run(
                create_cmd,
                input=passphrase.encode(),
                check=True,
                capture_output=True
            )
            
            # Verify VeraCrypt detection works
            vc_ver = crypto_engine.veracrypt_version(device)
            assert vc_ver == "veracrypt"
            
            # Verify NOT detected as LUKS
            luks_ver = crypto_engine.luks_version(device)
            assert luks_ver is None

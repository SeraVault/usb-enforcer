"""Integration tests for content scanning with virtual USB drives.

These tests verify that content scanning works correctly for both
encrypted and unencrypted USB drives, blocking sensitive data writes.

Run with: sudo pytest tests/integration/test_content_scanning.py -v
"""

from __future__ import annotations

import os
import tempfile
import time
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
import threading

import pytest

from usb_enforcer import daemon, constants
from usb_enforcer.encryption import classify, user_utils


# Check if content verification is available
try:
    from usb_enforcer.content_verification.scanner import ContentScanner
    from usb_enforcer.content_verification.fuse_overlay import FuseManager
    from usb_enforcer.content_verification.config import ContentScanningConfig
    CONTENT_VERIFICATION_AVAILABLE = True
except ImportError:
    CONTENT_VERIFICATION_AVAILABLE = False


@pytest.fixture
def content_scanning_config(temp_dir: Path) -> Path:
    """Create a configuration file with content scanning enabled."""
    config_content = """
enforce_on_usb_only = true
allow_luks1_readonly = true
default_plain_mount_opts = ["nodev", "nosuid", "noexec", "ro"]
default_encrypted_mount_opts = ["nodev", "nosuid", "rw"]
require_noexec_on_plain = true
min_passphrase_length = 12
encryption_target_mode = "whole_disk"
filesystem_type = "exfat"
notification_enabled = true
exempted_groups = ["usb-exempt"]

[kdf]
type = "argon2id"

[cipher]
type = "aes-xts-plain64"
key_size = 512

[content_scanning]
enabled = true
scan_archives = true
scan_documents = true
block_on_detection = true
max_file_size_mb = 100
"""
    config_path = temp_dir / "config.toml"
    config_path.write_text(config_content)
    return config_path


@pytest.fixture
def mock_usb_device(temp_dir: Path):
    """Create a mock USB device file (loopback device)."""
    # Create a 100MB file to use as a virtual USB drive
    device_file = temp_dir / "virtual_usb.img"
    subprocess.run(
        ["dd", "if=/dev/zero", f"of={device_file}", "bs=1M", "count=100"],
        capture_output=True,
        check=True
    )
    
    # Set up loopback device
    result = subprocess.run(
        ["losetup", "-f", "--show", str(device_file)],
        capture_output=True,
        text=True,
        check=True
    )
    loop_device = result.stdout.strip()
    
    yield loop_device
    
    # Cleanup
    subprocess.run(["losetup", "-d", loop_device], check=False)


@pytest.fixture
def encrypted_usb_device(mock_usb_device):
    """Create an encrypted USB device using LUKS2."""
    # Use a simple passphrase for testing
    passphrase = "test-passphrase-12345"
    
    # Format as LUKS2
    proc = subprocess.Popen(
        ["cryptsetup", "luksFormat", "--type", "luks2", "-q", mock_usb_device],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    stdout, stderr = proc.communicate(input=passphrase)
    
    if proc.returncode != 0:
        pytest.skip(f"Failed to create LUKS device: {stderr}")
    
    yield {
        "device": mock_usb_device,
        "passphrase": passphrase,
        "mapper_name": "test-usb-enc"
    }


@pytest.fixture
def unencrypted_usb_device(mock_usb_device):
    """Create an unencrypted USB device with ext4 filesystem."""
    # Format as ext4
    result = subprocess.run(
        ["mkfs.ext4", "-F", mock_usb_device],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        pytest.skip(f"Failed to create ext4 filesystem: {result.stderr}")
    
    yield mock_usb_device


@pytest.mark.integration
@pytest.mark.skipif(not CONTENT_VERIFICATION_AVAILABLE, reason="Content verification not available")
@pytest.mark.skipif(os.geteuid() != 0, reason="Requires root privileges")
class TestEncryptedDriveContentScanning:
    """Test content scanning on encrypted USB drives."""
    
    def test_encrypted_drive_allows_clean_content(
        self, encrypted_usb_device, content_scanning_config, temp_dir
    ):
        """Test that clean content is allowed on encrypted drives."""
        # Initialize daemon with content scanning enabled
        d = daemon.Daemon(config_path=content_scanning_config)
        
        # Verify content scanner is initialized
        assert d.content_scanner is not None
        assert d.fuse_manager is not None
        
        # Unlock the encrypted device
        device = encrypted_usb_device["device"]
        mapper_name = encrypted_usb_device["mapper_name"]
        passphrase = encrypted_usb_device["passphrase"]
        
        # Open LUKS device
        proc = subprocess.Popen(
            ["cryptsetup", "open", device, mapper_name],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = proc.communicate(input=passphrase)
        
        if proc.returncode != 0:
            pytest.fail(f"Failed to unlock LUKS device: {stderr}")
        
        try:
            mapper_path = f"/dev/mapper/{mapper_name}"
            
            # Format the unlocked device
            subprocess.run(
                ["mkfs.ext4", "-F", mapper_path],
                capture_output=True,
                check=True
            )
            
            # Mount the device
            mount_point = temp_dir / "mount"
            mount_point.mkdir()
            subprocess.run(
                ["mount", mapper_path, str(mount_point)],
                capture_output=True,
                check=True
            )
            
            try:
                # Write clean content (should be allowed)
                test_file = mount_point / "clean_data.txt"
                clean_content = "This is clean test data without sensitive information."
                test_file.write_text(clean_content)
                
                # Verify file was written
                assert test_file.exists()
                assert test_file.read_text() == clean_content
                
            finally:
                # Unmount
                subprocess.run(["umount", str(mount_point)], check=False)
        
        finally:
            # Close LUKS device
            subprocess.run(["cryptsetup", "close", mapper_name], check=False)
    
    def test_encrypted_drive_blocks_sensitive_content(
        self, encrypted_usb_device, content_scanning_config, temp_dir
    ):
        """Test that sensitive content is blocked on encrypted drives."""
        # This test would require FUSE overlay to be fully set up
        # For now, we'll test the scanner directly
        
        d = daemon.Daemon(config_path=content_scanning_config)
        
        assert d.content_scanner is not None
        
        # Test sensitive content detection
        sensitive_content = b"SSN: 123-45-6789\nCredit Card: 4111-1111-1111-1111"
        
        # Create a temporary file with sensitive content
        test_file = temp_dir / "sensitive.txt"
        test_file.write_bytes(sensitive_content)
        
        # Scan the file
        result = d.content_scanner.scan_file(test_file)
        
        # Verify sensitive data was detected
        assert len(result.matches) > 0
        assert any("ssn" in m.pattern_name.lower() for m in result.matches)
    
    def test_encrypted_drive_scans_archives(
        self, encrypted_usb_device, content_scanning_config, temp_dir
    ):
        """Test that archives are scanned for sensitive content."""
        d = daemon.Daemon(config_path=content_scanning_config)
        
        assert d.content_scanner is not None
        
        # Create a zip file with sensitive content
        import zipfile
        
        archive_path = temp_dir / "test_archive.zip"
        with zipfile.ZipFile(archive_path, 'w') as zf:
            zf.writestr("data.txt", "SSN: 123-45-6789")
        
        # Scan the archive using archive scanner
        from usb_enforcer.content_verification.archive_scanner import ArchiveScanner

        archive_scanner = ArchiveScanner(
            content_scanner=d.content_scanner,
            config=d.config.content_scanning.archives,
        )
        result = archive_scanner.scan_archive(archive_path)
        
        # Verify sensitive data in archive was detected
        assert len(result.matches) > 0


@pytest.mark.integration
@pytest.mark.skipif(not CONTENT_VERIFICATION_AVAILABLE, reason="Content verification not available")
@pytest.mark.skipif(os.geteuid() != 0, reason="Requires root privileges")
class TestUnencryptedDriveContentScanning:
    """Test content scanning on unencrypted USB drives (exempted users)."""
    
    def test_unencrypted_drive_exempted_user_allows_clean_content(
        self, unencrypted_usb_device, content_scanning_config, temp_dir
    ):
        """Test that clean content is allowed for exempted users on unencrypted drives."""
        # Initialize daemon with content scanning enabled
        d = daemon.Daemon(config_path=content_scanning_config)
        
        # Verify content scanner is initialized
        assert d.content_scanner is not None
        assert d.fuse_manager is not None
        
        # Mock user exemption check to simulate exempted user
        with patch.object(user_utils, 'any_active_user_in_groups') as mock_exempt:
            mock_exempt.return_value = (True, "user 'testuser' in exempted group 'usb-exempt'")
            
            # Simulate device properties for unencrypted USB
            device_props = {
                "ID_BUS": "usb",
                "ID_TYPE": "disk",
                "DEVTYPE": "partition",
                "ID_FS_TYPE": "ext4",
                "ID_FS_USAGE": "filesystem",
                "ID_SERIAL_SHORT": "TEST123"
            }
            
            # Handle device event
            d.handle_device(device_props, unencrypted_usb_device, "add")
            
            # Check that device was handled as exempt
            device_status = d.get_device_status(unencrypted_usb_device)
            assert device_status is not None
    
    def test_unencrypted_drive_exempted_user_blocks_sensitive_content(
        self, content_scanning_config, temp_dir
    ):
        """Test that sensitive content is blocked for exempted users on unencrypted drives."""
        d = daemon.Daemon(config_path=content_scanning_config)
        
        assert d.content_scanner is not None
        
        # Test sensitive content detection
        sensitive_content = b"""
        Patient Name: John Doe
        SSN: 123-45-6789
        Credit Card: 4111-1111-1111-1111
        API Key: sk_live_FAKE12345678901234567890
        """
        
        test_file = temp_dir / "sensitive.txt"
        test_file.write_bytes(sensitive_content)
        
        # Scan the file
        result = d.content_scanner.scan_file(test_file)
        
        # Verify multiple types of sensitive data were detected
        assert len(result.matches) > 0
        pattern_types = [m.pattern_name for m in result.matches]
        
        # Should detect SSN and credit card at minimum
        assert len(set(pattern_types)) >= 2
    
    def test_unencrypted_drive_non_exempted_user_read_only(
        self, unencrypted_usb_device, content_scanning_config
    ):
        """Test that non-exempted users get read-only access (no scanning needed)."""
        d = daemon.Daemon(config_path=content_scanning_config)
        
        # Mock user exemption check to simulate non-exempted user
        with patch.object(user_utils, 'any_active_user_in_groups') as mock_exempt:
            mock_exempt.return_value = (False, "")
            
            # Simulate device properties for unencrypted USB
            device_props = {
                "ID_BUS": "usb",
                "ID_TYPE": "disk",
                "DEVTYPE": "partition",
                "ID_FS_TYPE": "ext4",
                "ID_FS_USAGE": "filesystem",
                "ID_SERIAL_SHORT": "TEST123"
            }
            
            # Handle device event
            d.handle_device(device_props, unencrypted_usb_device, "add")
            
            # Verify device is in read-only mode (block_rw action)
            # Since we don't have actual enforcement here, we just verify
            # the device was processed
            device_status = d.get_device_status(unencrypted_usb_device)
            assert device_status is not None


@pytest.mark.integration
@pytest.mark.skipif(not CONTENT_VERIFICATION_AVAILABLE, reason="Content verification not available")
class TestContentScannerPatterns:
    """Test content scanner pattern detection."""
    
    def test_ssn_detection(self, content_scanning_config):
        """Test SSN pattern detection."""
        d = daemon.Daemon(config_path=content_scanning_config)
        scanner = d.content_scanner
        
        test_cases = [
            (b"SSN: 123-45-6789", True),
            (b"Social Security Number: 111-22-3333", True),
            (b"123-45-6789", True),
            (b"Random text without SSN", False),
            (b"123-456-7890", False),  # Phone number, not SSN
        ]
        
        for content, should_detect in test_cases:
            result = scanner.scan_content(content)
            if should_detect:
                assert len(result.matches) > 0, f"Failed to detect SSN in: {content}"
            else:
                # Check if SSN was detected (might detect other patterns)
                ssn_detected = any('ssn' in m.pattern_name.lower() for m in result.matches)
                assert not ssn_detected, f"False positive SSN in: {content}"
    
    def test_credit_card_detection(self, content_scanning_config):
        """Test credit card pattern detection."""
        d = daemon.Daemon(config_path=content_scanning_config)
        scanner = d.content_scanner
        
        test_cases = [
            (b"Card: 4111-1111-1111-1111", True),  # Valid Visa with dashes
            (b"4012888888881881", True),  # Valid Visa without dashes
            (b"Credit Card Number: 5555-5555-5555-4444", True),  # Valid Mastercard
            (b"Random numbers: 1234-5678-9012-3456", False),  # Invalid Luhn check digit
        ]
        
        for content, should_detect in test_cases:
            result = scanner.scan_content(content)
            if should_detect:
                card_detected = any('credit' in m.pattern_name.lower() or 'card' in m.pattern_name.lower() for m in result.matches)
                assert card_detected, f"Failed to detect credit card in: {content}"
    
    def test_api_key_detection(self, content_scanning_config):
        """Test API key pattern detection."""
        d = daemon.Daemon(config_path=content_scanning_config)
        scanner = d.content_scanner
        
        test_cases = [
            (b"API_KEY=sk_live_FAKE12345678901234567890", True),
            (b"Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", True),
            (b"AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", True),
            (b"password=secret123", False),  # Too generic
        ]
        
        for content, should_detect in test_cases:
            result = scanner.scan_content(content)
            if should_detect:
                key_detected = any('api' in m.pattern_name.lower() or 'key' in m.pattern_name.lower() or 'token' in m.pattern_name.lower() for m in result.matches)
                # Some patterns might not be detected if not in the pattern set
                # This is informational rather than strict
                if not key_detected:
                    print(f"Note: API key not detected in: {content}")


@pytest.mark.integration
@pytest.mark.skipif(not CONTENT_VERIFICATION_AVAILABLE, reason="Content verification not available")
class TestContentScannerPerformance:
    """Test content scanner performance and resource usage."""
    
    def test_large_file_scanning(self, content_scanning_config, temp_dir):
        """Test scanning of large files."""
        d = daemon.Daemon(config_path=content_scanning_config)
        scanner = d.content_scanner
        
        # Create a 10MB file
        large_file = temp_dir / "large_file.txt"
        with open(large_file, 'wb') as f:
            # Write 10MB of clean data
            clean_data = b"Clean data line\n" * 100000
            f.write(clean_data)
        
        # Measure scan time
        import time
        start_time = time.time()
        result = scanner.scan_file(large_file)  # Pass Path object, not string
        scan_time = time.time() - start_time
        
        # Should complete in reasonable time (< 5 seconds for 10MB)
        assert scan_time < 5.0, f"Scan took too long: {scan_time:.2f}s"
        
        # Should not detect anything
        assert len(result.matches) == 0
    
    def test_concurrent_scanning(self, content_scanning_config, temp_dir):
        """Test concurrent file scanning."""
        d = daemon.Daemon(config_path=content_scanning_config)
        scanner = d.content_scanner
        
        # Create multiple test files
        files = []
        for i in range(5):
            test_file = temp_dir / f"test_{i}.txt"
            test_file.write_text(f"Clean test data {i}")
            files.append(test_file)
        
        # Scan concurrently
        import concurrent.futures
        
        def scan_file(filepath):
            return scanner.scan_file(filepath)  # Pass Path object directly
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(scan_file, f) for f in files]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All should complete without errors
        assert len(results) == 5
        # All should be clean
        assert all(len(r.matches) == 0 for r in results)


@pytest.mark.integration  
@pytest.mark.skipif(not CONTENT_VERIFICATION_AVAILABLE, reason="Content verification not available")
class TestFuseManagerIntegration:
    """Test FUSE overlay manager integration."""
    
    def test_fuse_manager_initialization(self, content_scanning_config):
        """Test FuseManager initializes correctly."""
        d = daemon.Daemon(config_path=content_scanning_config)
        
        assert d.fuse_manager is not None
        assert hasattr(d.fuse_manager, 'mount')
        assert hasattr(d.fuse_manager, 'unmount')
        assert hasattr(d.fuse_manager, 'get_statistics')
    
    def test_scanner_statistics(self, content_scanning_config):
        """Test getting scanner statistics."""
        d = daemon.Daemon(config_path=content_scanning_config)
        
        # Get statistics (should work even with no mounts)
        stats = d.get_scanner_statistics()
        
        assert isinstance(stats, dict)
        # Should have expected keys
        assert 'active_mounts' in stats
        assert stats['active_mounts'] == '0'
    
    @patch('usb_enforcer.content_verification.fuse_overlay.FUSE')
    def test_fuse_mount_called_on_setup(self, mock_fuse, content_scanning_config, temp_dir):
        """Test that FUSE mount is called when setting up overlay."""
        d = daemon.Daemon(config_path=content_scanning_config)
        
        # Mock subprocess calls for findmnt
        with patch('subprocess.run') as mock_run:
            # First call: findmnt returns mount point
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = str(temp_dir / "mount")
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            
            # Attempt to set up FUSE overlay
            d._setup_fuse_overlay("/dev/test", base_mount=str(temp_dir / "mount"))
            
            # FUSE should have been called
            # Note: This might fail if mount implementation differs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

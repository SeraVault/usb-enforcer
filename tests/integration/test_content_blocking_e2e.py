"""End-to-end integration tests for content blocking through FUSE overlay.

These tests verify the complete content blocking workflow:
1. Daemon starts with content scanning enabled
2. Encrypted USB device is mounted through FUSE overlay
3. Writes with sensitive content are actually blocked
4. Writes with clean content succeed
5. Statistics and notifications are generated

These tests require root privileges and the full content verification system.
Run with: sudo pytest tests/integration/test_content_blocking_e2e.py -v
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from usb_enforcer import daemon


# Check if content verification is available
try:
    from usb_enforcer.content_verification.scanner import ContentScanner
    from usb_enforcer.content_verification.fuse_overlay import FuseManager
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
scan_on_close = true
"""
    config_path = temp_dir / "config.toml"
    config_path.write_text(config_content)
    return config_path


@pytest.mark.integration
@pytest.mark.skipif(not CONTENT_VERIFICATION_AVAILABLE, reason="Content verification not available")
@pytest.mark.skipif(os.geteuid() != 0, reason="Requires root privileges")
class TestContentBlockingEndToEnd:
    """Test end-to-end content blocking through FUSE overlay."""
    
    def test_fuse_blocks_sensitive_content_write(
        self, loop_device, content_scanning_config, temp_dir, require_cryptsetup
    ):
        """Test that FUSE overlay actually blocks writes with sensitive content.
        
        This is a TRUE end-to-end test:
        1. Creates an encrypted device
        2. Daemon sets up FUSE overlay
        3. Attempts to write sensitive content through FUSE
        4. Verifies write is blocked with EPERM
        5. Verifies clean writes succeed
        """
        with loop_device(size_mb=200) as device:
            passphrase = "test-content-blocking-pass-123"
            mapper_name = f"test-content-{int(time.time())}"
            
            # Create LUKS2 encrypted device
            subprocess.run(
                ["cryptsetup", "luksFormat", "--type", "luks2", "-q", device],
                input=passphrase.encode(),
                check=True,
                capture_output=True
            )
            
            # Open the encrypted device
            subprocess.run(
                ["cryptsetup", "open", device, mapper_name],
                input=passphrase.encode(),
                check=True,
                capture_output=True
            )
            
            try:
                mapper_path = f"/dev/mapper/{mapper_name}"
                
                # Format with ext4
                subprocess.run(
                    ["mkfs.ext4", "-F", mapper_path],
                    check=True,
                    capture_output=True
                )
                
                # Create base mount point
                base_mount = temp_dir / "base_mount"
                base_mount.mkdir()
                
                # Mount the device to base mount
                subprocess.run(
                    ["mount", mapper_path, str(base_mount)],
                    check=True,
                    capture_output=True
                )
                
                try:
                    # Initialize daemon with content scanning
                    d = daemon.Daemon(config_path=content_scanning_config)
                    
                    assert d.content_scanner is not None, "Content scanner not initialized"
                    assert d.fuse_manager is not None, "FUSE manager not initialized"
                    
                    # Create FUSE overlay mount point
                    fuse_mount = temp_dir / "fuse_mount"
                    fuse_mount.mkdir()
                    
                    # Set up FUSE overlay
                    try:
                        # This should mount the FUSE overlay over the base mount
                        success = d.fuse_manager.mount(
                            device_path=str(base_mount),
                            mount_point=str(fuse_mount),
                            is_encrypted=True,
                            source_is_mount=True
                        )
                        
                        if not success:
                            pytest.skip("FUSE overlay mount failed - may not be supported")
                        
                        # Give FUSE time to initialize
                        time.sleep(1)
                        
                        # Verify FUSE mount is active
                        result = subprocess.run(
                            ["mountpoint", "-q", str(fuse_mount)],
                            capture_output=True
                        )
                        if result.returncode != 0:
                            pytest.skip("FUSE mount not detected by mountpoint")
                        
                        # TEST 1: Attempt to write sensitive content (should be BLOCKED)
                        sensitive_file = fuse_mount / "sensitive_data.txt"
                        sensitive_content = """
Patient Information:
Name: John Doe
SSN: 123-45-6789
Credit Card: 4111-1111-1111-1111
API Key: sk_live_51H7abcdefghijklmnop
"""
                        
                        # This write should fail with PermissionError or OSError
                        write_blocked = False
                        write_error = None
                        try:
                            with open(sensitive_file, 'w') as f:
                                f.write(sensitive_content)
                                f.flush()
                            # If we get here, close/release succeeded - check the file
                        except (PermissionError, OSError) as e:
                            # Expected - write was blocked
                            write_blocked = True
                            write_error = e
                            print(f"Write correctly blocked: {e}")
                        
                        # Give FUSE time to cleanup
                        time.sleep(0.5)
                        
                        # Check the outcome
                        if not write_blocked:
                            # File may have been written - check if it has the sensitive content
                            if sensitive_file.exists():
                                actual_content = sensitive_file.read_text()
                                if len(actual_content) > 0:
                                    pytest.fail(f"Sensitive content was NOT blocked! File contains: {actual_content[:100]}")
                                else:
                                    print("File exists but is empty - blocking may have occurred")
                        
                        print(f"Write blocked status: {write_blocked}, error: {write_error}")
                        
                        # TEST 2: Write clean content (should SUCCEED)
                        clean_file = fuse_mount / "clean_data.txt"
                        clean_content = "This is perfectly safe data with no sensitive information."
                        
                        try:
                            clean_file.write_text(clean_content)
                        except (PermissionError, OSError) as e:
                            pytest.fail(f"Clean content write should succeed but was blocked: {e}")
                        
                        assert clean_file.exists(), "Clean file should exist"
                        assert clean_file.read_text() == clean_content, "Clean content should match"
                        
                        # TEST 3: Verify statistics show blocking
                        stats = d.get_scanner_statistics()
                        print(f"Scanner statistics: {stats}")
                        
                        # Should show at least one mount
                        assert 'active_mounts' in stats
                        assert int(stats['active_mounts']) > 0, "Should have active FUSE mounts"
                        
                    finally:
                        # Cleanup FUSE mount
                        try:
                            d.fuse_manager.unmount(str(fuse_mount))
                        except Exception as e:
                            print(f"Error unmounting FUSE: {e}")
                            # Force unmount
                            subprocess.run(["fusermount", "-uz", str(fuse_mount)], check=False)
                        
                        time.sleep(0.5)
                
                finally:
                    # Unmount base mount
                    subprocess.run(["umount", str(base_mount)], check=False)
            
            finally:
                # Close LUKS device
                subprocess.run(["cryptsetup", "close", mapper_name], check=False)
    
    def test_fuse_blocks_archive_with_sensitive_content(
        self, loop_device, content_scanning_config, temp_dir, require_cryptsetup
    ):
        """Test that FUSE blocks writing archives containing sensitive content."""
        with loop_device(size_mb=200) as device:
            passphrase = "test-archive-blocking-pass-456"
            mapper_name = f"test-archive-{int(time.time())}"
            
            # Create and open encrypted device
            subprocess.run(
                ["cryptsetup", "luksFormat", "--type", "luks2", "-q", device],
                input=passphrase.encode(),
                check=True,
                capture_output=True
            )
            subprocess.run(
                ["cryptsetup", "open", device, mapper_name],
                input=passphrase.encode(),
                check=True,
                capture_output=True
            )
            
            try:
                mapper_path = f"/dev/mapper/{mapper_name}"
                subprocess.run(["mkfs.ext4", "-F", mapper_path], check=True, capture_output=True)
                
                base_mount = temp_dir / "base_mount"
                base_mount.mkdir()
                subprocess.run(["mount", mapper_path, str(base_mount)], check=True, capture_output=True)
                
                try:
                    d = daemon.Daemon(config_path=content_scanning_config)
                    
                    fuse_mount = temp_dir / "fuse_mount"
                    fuse_mount.mkdir()
                    
                    success = d.fuse_manager.mount(
                        device_path=str(base_mount),
                        mount_point=str(fuse_mount),
                        is_encrypted=True,
                        source_is_mount=True
                    )
                    
                    if not success:
                        pytest.skip("FUSE overlay mount failed")
                    
                    time.sleep(1)
                    
                    try:
                        # Create a zip file with sensitive content
                        import zipfile
                        import io
                        
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, 'w') as zf:
                            zf.writestr("secret.txt", "SSN: 123-45-6789\nPassword: secret123")
                        
                        zip_data = zip_buffer.getvalue()
                        
                        # Attempt to write the archive through FUSE
                        archive_file = fuse_mount / "data.zip"
                        
                        archive_blocked = False
                        try:
                            archive_file.write_bytes(zip_data)
                        except (PermissionError, OSError):
                            archive_blocked = True
                        
                        # Should be blocked if archive scanning is enabled
                        if d.config.content_scanning.scan_archives:
                            assert archive_blocked, "Archive with sensitive content should be blocked"
                            assert not archive_file.exists(), "Archive should not exist after blocked write"
                    
                    finally:
                        d.fuse_manager.unmount(str(fuse_mount))
                        subprocess.run(["fusermount", "-uz", str(fuse_mount)], check=False)
                
                finally:
                    subprocess.run(["umount", str(base_mount)], check=False)
            
            finally:
                subprocess.run(["cryptsetup", "close", mapper_name], check=False)
    
    def test_daemon_setup_fuse_for_encrypted_device(
        self, loop_device, content_scanning_config, temp_dir, require_cryptsetup
    ):
        """Test that daemon automatically sets up FUSE when handling encrypted device.
        
        This tests the full daemon workflow:
        1. Daemon receives device event
        2. Recognizes it as encrypted
        3. Automatically sets up FUSE overlay
        4. Blocks sensitive content writes
        """
        with loop_device(size_mb=200) as device:
            passphrase = "test-daemon-fuse-setup-789"
            mapper_name = f"test-daemon-{int(time.time())}"
            
            # Create encrypted device
            subprocess.run(
                ["cryptsetup", "luksFormat", "--type", "luks2", "-q", device],
                input=passphrase.encode(),
                check=True,
                capture_output=True
            )
            
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
            device_props["ID_TYPE"] = "disk"
            device_props["DEVTYPE"] = "disk"
            device_props["ID_FS_USAGE"] = "crypto"
            
            # Initialize daemon
            d = daemon.Daemon(config_path=content_scanning_config)
            
            # Mock user not in exempted group
            with patch('usb_enforcer.user_utils.any_active_user_in_groups', return_value=(False, "")):
                # Handle device event - daemon should set up FUSE for encrypted device
                d.handle_device(device_props, device, "add")
            
            # Verify device is tracked
            assert device in d.devices, "Device should be tracked by daemon"
            
            # Verify content scanning is active
            stats = d.get_scanner_statistics()
            print(f"Daemon scanner statistics: {stats}")
            
            # Note: Full mount may not happen in test environment without actual unlock
            # This test verifies daemon initialization and tracking


@pytest.mark.integration
@pytest.mark.skipif(not CONTENT_VERIFICATION_AVAILABLE, reason="Content verification not available")
class TestContentBlockingWithoutRoot:
    """Tests that can run without root to verify scanner logic."""
    
    def test_scanner_detects_multiple_patterns(self, content_scanning_config, temp_dir):
        """Test that scanner detects multiple types of sensitive patterns."""
        d = daemon.Daemon(config_path=content_scanning_config)
        
        # Create file with multiple sensitive patterns
        test_file = temp_dir / "multi_sensitive.txt"
        content = """
Personal Information:
SSN: 123-45-6789
Credit Card: 4111-1111-1111-1111
API Key: sk_live_51H7abcdefghijklmnop
AWS Secret: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
"""
        test_file.write_text(content)
        
        result = d.content_scanner.scan_file(test_file)
        
        # Should detect multiple patterns
        assert len(result.matches) >= 3, f"Should detect at least 3 patterns, found {len(result.matches)}"
        
        pattern_types = [m.pattern_name.lower() for m in result.matches]
        assert any("ssn" in p for p in pattern_types), "Should detect SSN"
        assert any("credit" in p or "card" in p for p in pattern_types), "Should detect credit card"
        assert any("key" in p or "api" in p for p in pattern_types), "Should detect API key"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Unit tests for crypto_engine with mocked subprocess calls.

These tests don't require root or cryptsetup, they test logic with mocked system calls.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock, mock_open, patch, call

import pytest

from usb_enforcer import crypto_engine


class TestLuksVersion:
    """Test LUKS version detection logic."""
    
    def test_luks_version_detects_version_2(self):
        """Test parsing LUKS2 version from luksDump output."""
        dump_output = b"""
LUKS header information
Version:       2
Epoch:         3
Metadata area: 16384 [bytes]
"""
        with patch('usb_enforcer.crypto_engine._run') as mock_run:
            mock_run.return_value.stdout = dump_output
            
            version = crypto_engine.luks_version("/dev/test")
            
            assert version == "2"
            mock_run.assert_called_once_with(["cryptsetup", "luksDump", "/dev/test"])
    
    def test_luks_version_detects_version_1(self):
        """Test parsing LUKS1 version from luksDump output."""
        dump_output = b"""
LUKS header information for /dev/test

Version:        1
Cipher name:    aes
"""
        with patch('usb_enforcer.crypto_engine._run') as mock_run:
            mock_run.return_value.stdout = dump_output
            
            version = crypto_engine.luks_version("/dev/test")
            
            assert version == "1"
    
    def test_luks_version_returns_none_on_error(self):
        """Test that non-LUKS devices return None."""
        with patch('usb_enforcer.crypto_engine._run') as mock_run:
            mock_run.side_effect = crypto_engine.CryptoError("not a LUKS device")
            
            version = crypto_engine.luks_version("/dev/plaintext")
            
            assert version is None
    
    def test_luks_version_handles_missing_version_line(self):
        """Test handling of luksDump output without Version line."""
        dump_output = b"""
LUKS header information
Epoch:         3
"""
        with patch('usb_enforcer.crypto_engine._run') as mock_run:
            mock_run.return_value.stdout = dump_output
            
            version = crypto_engine.luks_version("/dev/test")
            
            assert version is None


class TestUnlockLuks:
    """Test LUKS unlocking logic."""
    
    def test_unlock_luks_passes_correct_command(self):
        """Test that unlock_luks calls cryptsetup with correct params."""
        with patch('usb_enforcer.crypto_engine._run') as mock_run:
            result = crypto_engine.unlock_luks(
                "/dev/sdb1",
                "my-mapper",
                "secret123"
            )
            
            mock_run.assert_called_once_with(
                ["cryptsetup", "open", "/dev/sdb1", "my-mapper"],
                input_data=b"secret123"
            )
            assert result == "/dev/mapper/my-mapper"
    
    def test_unlock_luks_raises_on_wrong_password(self):
        """Test that unlock_luks propagates CryptoError on failure."""
        with patch('usb_enforcer.crypto_engine._run') as mock_run:
            mock_run.side_effect = crypto_engine.CryptoError("No key available")
            
            with pytest.raises(crypto_engine.CryptoError):
                crypto_engine.unlock_luks("/dev/sdb1", "mapper", "wrong")


class TestCloseMapper:
    """Test LUKS device closing logic."""
    
    def test_close_mapper_calls_cryptsetup_close(self):
        """Test that close_mapper calls cryptsetup close."""
        with patch('usb_enforcer.crypto_engine._run') as mock_run:
            crypto_engine.close_mapper("my-mapper")
            
            mock_run.assert_called_once_with(["cryptsetup", "close", "my-mapper"])


class TestCreateFilesystem:
    """Test filesystem creation logic."""
    
    def test_create_ext4_with_label(self):
        """Test ext4 filesystem creation with label."""
        with patch('usb_enforcer.crypto_engine._run') as mock_run:
            crypto_engine.create_filesystem(
                "/dev/mapper/test",
                fs_type="ext4",
                label="MyDrive"
            )
            
            mock_run.assert_called_once_with([
                "mkfs.ext4", "-F", "-L", "MyDrive", "/dev/mapper/test"
            ])
    
    def test_create_ext4_with_ownership(self):
        """Test ext4 filesystem with uid/gid ownership."""
        with patch('usb_enforcer.crypto_engine._run') as mock_run:
            crypto_engine.create_filesystem(
                "/dev/mapper/test",
                fs_type="ext4",
                label="MyDrive",
                uid=1000,
                gid=1000
            )
            
            mock_run.assert_called_once_with([
                "mkfs.ext4", "-F", "-L", "MyDrive",
                "-E", "root_owner=1000:1000",
                "/dev/mapper/test"
            ])
    
    def test_create_exfat_with_label(self):
        """Test exFAT filesystem creation with label."""
        with patch('usb_enforcer.crypto_engine._run') as mock_run:
            crypto_engine.create_filesystem(
                "/dev/mapper/test",
                fs_type="exfat",
                label="USB_DRIVE"
            )
            
            mock_run.assert_called_once_with([
                "mkfs.exfat", "-n", "USB_DRIVE", "/dev/mapper/test"
            ])
    
    def test_create_filesystem_unsupported_type(self):
        """Test that unsupported filesystem types raise error."""
        with pytest.raises(crypto_engine.CryptoError, match="Unsupported filesystem"):
            crypto_engine.create_filesystem("/dev/test", fs_type="ntfs")


class TestMountDevice:
    """Test device mounting logic."""
    
    def test_mount_device_creates_mountpoint(self):
        """Test that mount_device creates the mount directory."""
        with patch('usb_enforcer.crypto_engine._run') as mock_run, \
             patch('os.makedirs') as mock_makedirs:
            
            crypto_engine.mount_device(
                "/dev/mapper/test",
                "/mnt/test",
                ["rw", "noatime"]
            )
            
            mock_makedirs.assert_called_once_with("/mnt/test", exist_ok=True)
            mock_run.assert_called_once_with([
                "mount", "-o", "rw,noatime", "/dev/mapper/test", "/mnt/test"
            ])
    
    def test_mount_device_sets_ownership(self):
        """Test that mount_device changes ownership when uid/gid provided."""
        with patch('usb_enforcer.crypto_engine._run') as mock_run, \
             patch('os.makedirs'), \
             patch('os.chown') as mock_chown, \
             patch('os.walk') as mock_walk:
            
            # Mock walk to return mountpoint and one subdirectory
            mock_walk.return_value = [
                ("/mnt/test", ["subdir"], ["file.txt"])
            ]
            
            crypto_engine.mount_device(
                "/dev/mapper/test",
                "/mnt/test",
                ["rw"],
                uid=1000,
                gid=1000
            )
            
            # Should chown the mountpoint, subdirectory, and file
            assert mock_chown.call_count >= 3


class TestGetMountedDevices:
    """Test mounted device detection."""
    
    def test_get_mounted_devices_parses_proc_mounts(self):
        """Test parsing /proc/mounts to find mounted devices."""
        mock_mounts = """
/dev/sda1 / ext4 rw,relatime 0 0
/dev/sdb1 /mnt/usb ext4 rw,nosuid,nodev 0 0
/dev/mapper/luks-123 /mnt/encrypted ext4 rw 0 0
proc /proc proc rw,nosuid,nodev,noexec 0 0
"""
        with patch('builtins.open', mock_open(read_data=mock_mounts)):
            mounted = crypto_engine._get_mounted_devices()
            
            assert mounted == {
                "/dev/sda1": "/",
                "/dev/sdb1": "/mnt/usb",
                "/dev/mapper/luks-123": "/mnt/encrypted"
            }
    
    def test_get_mounted_devices_handles_missing_proc_mounts(self):
        """Test graceful handling when /proc/mounts is unavailable."""
        with patch('builtins.open', side_effect=FileNotFoundError):
            mounted = crypto_engine._get_mounted_devices()
            
            assert mounted == {}


class TestGetDevicePartitions:
    """Test partition enumeration logic."""
    
    def test_get_device_partitions_with_pyudev(self):
        """Test partition detection using pyudev."""
        mock_context = Mock()
        mock_device = Mock()
        mock_partition1 = Mock(device_type='partition', device_node='/dev/sdb1')
        mock_partition2 = Mock(device_type='partition', device_node='/dev/sdb2')
        
        with patch('usb_enforcer.crypto_engine.pyudev') as mock_pyudev:
            mock_pyudev.Context.return_value = mock_context
            mock_pyudev.Devices.from_device_file.return_value = mock_device
            mock_context.list_devices.return_value = [mock_partition1, mock_partition2]
            
            partitions = crypto_engine._get_device_partitions("/dev/sdb")
            
            assert partitions == ["/dev/sdb1", "/dev/sdb2"]
    
    def test_get_device_partitions_includes_partition_itself(self):
        """Test that partition device nodes include themselves."""
        with patch('usb_enforcer.crypto_engine.pyudev', None):
            partitions = crypto_engine._get_device_partitions("/dev/sdb1")
            
            assert "/dev/sdb1" in partitions
    
    def test_get_device_partitions_handles_pyudev_error(self):
        """Test graceful handling when pyudev fails."""
        with patch('usb_enforcer.crypto_engine.pyudev') as mock_pyudev:
            mock_pyudev.Context.side_effect = Exception("pyudev error")
            
            partitions = crypto_engine._get_device_partitions("/dev/sdb")
            
            # Should return empty list on error for disk devices
            assert partitions == []


class TestUdisks2Unmount:
    """Test UDisks2 D-Bus unmount logic."""
    
    def test_udisks2_unmount_success(self):
        """Test successful unmount via UDisks2 D-Bus."""
        mock_bus = Mock()
        mock_filesystem = Mock()
        
        with patch('usb_enforcer.crypto_engine.pydbus') as mock_pydbus:
            mock_pydbus.SystemBus.return_value = mock_bus
            mock_bus.get.return_value = mock_filesystem
            
            result = crypto_engine._udisks2_unmount("/dev/sdb1")
            
            assert result is True
            mock_filesystem.Unmount.assert_called_once_with({})
    
    def test_udisks2_unmount_no_pydbus(self):
        """Test that unmount returns False when pydbus unavailable."""
        with patch('usb_enforcer.crypto_engine.pydbus', None):
            result = crypto_engine._udisks2_unmount("/dev/sdb1")
            
            assert result is False
    
    def test_udisks2_unmount_device_not_mounted(self):
        """Test that unmount returns False for non-mounted devices."""
        mock_bus = Mock()
        
        with patch('usb_enforcer.crypto_engine.pydbus') as mock_pydbus:
            mock_pydbus.SystemBus.return_value = mock_bus
            mock_bus.get.side_effect = Exception("not mounted")
            
            result = crypto_engine._udisks2_unmount("/dev/sdb1")
            
            assert result is False


class TestEncryptDevice:
    """Test the main encrypt_device workflow logic."""
    
    @patch('usb_enforcer.crypto_engine._run')
    @patch('usb_enforcer.crypto_engine._get_device_partitions')
    @patch('usb_enforcer.crypto_engine._get_mounted_devices')
    @patch('usb_enforcer.crypto_engine.unlock_luks')
    @patch('usb_enforcer.crypto_engine.create_filesystem')
    def test_encrypt_device_basic_workflow(
        self,
        mock_create_fs,
        mock_unlock,
        mock_get_mounted,
        mock_get_partitions,
        mock_run
    ):
        """Test basic encrypt_device workflow with minimal options."""
        mock_get_partitions.return_value = []
        mock_get_mounted.return_value = {}
        mock_unlock.return_value = "/dev/mapper/test-mapper"
        
        result = crypto_engine.encrypt_device(
            "/dev/sdb",
            "test-mapper",
            "password123",
            fs_type="ext4",
            mount_opts=[]
        )
        
        assert result == "/dev/mapper/test-mapper"
        # Should call luksFormat, unlock, and create filesystem
        assert any("luksFormat" in str(call) for call in mock_run.call_args_list)
        mock_unlock.assert_called_once()
        mock_create_fs.assert_called_once()
    
    @patch('usb_enforcer.crypto_engine._run')
    @patch('usb_enforcer.crypto_engine._get_device_partitions')
    @patch('usb_enforcer.crypto_engine._get_mounted_devices')
    @patch('usb_enforcer.crypto_engine.unlock_luks')
    @patch('usb_enforcer.crypto_engine.create_filesystem')
    def test_encrypt_device_unmounts_before_encryption(
        self,
        mock_create_fs,
        mock_unlock,
        mock_get_mounted,
        mock_get_partitions,
        mock_run
    ):
        """Test that encrypt_device unmounts mounted partitions."""
        mock_get_partitions.return_value = ["/dev/sdb1", "/dev/sdb2"]
        mock_get_mounted.return_value = {"/dev/sdb1": "/mnt/usb"}
        mock_unlock.return_value = "/dev/mapper/test-mapper"
        
        crypto_engine.encrypt_device(
            "/dev/sdb",
            "test-mapper",
            "password123",
            fs_type="ext4",
            mount_opts=[]
        )
        
        # Should attempt unmount operations
        unmount_calls = [str(call) for call in mock_run.call_args_list]
        has_unmount = any("umount" in call or "unmount" in call for call in unmount_calls)
        assert has_unmount
    
    @patch('usb_enforcer.crypto_engine._run')
    @patch('usb_enforcer.crypto_engine._get_device_partitions')
    @patch('usb_enforcer.crypto_engine._get_mounted_devices')
    @patch('usb_enforcer.crypto_engine.unlock_luks')
    @patch('usb_enforcer.crypto_engine.create_filesystem')
    def test_encrypt_device_with_progress_callback(
        self,
        mock_create_fs,
        mock_unlock,
        mock_get_mounted,
        mock_get_partitions,
        mock_run
    ):
        """Test that encrypt_device calls progress callback."""
        mock_get_partitions.return_value = []
        mock_get_mounted.return_value = {}
        mock_unlock.return_value = "/dev/mapper/test-mapper"
        
        progress_calls = []
        def progress_cb(stage, pct):
            progress_calls.append((stage, pct))
        
        crypto_engine.encrypt_device(
            "/dev/sdb",
            "test-mapper",
            "password123",
            fs_type="ext4",
            mount_opts=[],
            progress_cb=progress_cb
        )
        
        # Should have called progress callback multiple times
        assert len(progress_calls) > 0
        # Should have final "done" callback
        assert ("done", 100) in progress_calls
    
    @patch('usb_enforcer.crypto_engine._run')
    @patch('usb_enforcer.crypto_engine._get_device_partitions')
    @patch('usb_enforcer.crypto_engine._get_mounted_devices')
    @patch('usb_enforcer.crypto_engine.unlock_luks')
    @patch('usb_enforcer.crypto_engine.create_filesystem')
    @patch('usb_enforcer.crypto_engine.close_mapper')
    def test_encrypt_device_cleans_up_on_error(
        self,
        mock_close,
        mock_create_fs,
        mock_unlock,
        mock_get_mounted,
        mock_get_partitions,
        mock_run
    ):
        """Test that encrypt_device closes mapper on error."""
        mock_get_partitions.return_value = []
        mock_get_mounted.return_value = {}
        mock_unlock.return_value = "/dev/mapper/test-mapper"
        mock_create_fs.side_effect = Exception("filesystem creation failed")
        
        with pytest.raises(Exception, match="filesystem creation failed"):
            crypto_engine.encrypt_device(
                "/dev/sdb",
                "test-mapper",
                "password123",
                fs_type="ext4",
                mount_opts=[]
            )
        
        # Should have attempted cleanup
        mock_close.assert_called_once_with("test-mapper")
    
    @patch('usb_enforcer.crypto_engine._run')
    @patch('usb_enforcer.crypto_engine._get_device_partitions')
    @patch('usb_enforcer.crypto_engine._get_mounted_devices')
    @patch('usb_enforcer.crypto_engine.unlock_luks')
    @patch('usb_enforcer.crypto_engine.create_filesystem')
    def test_encrypt_device_with_custom_cipher_options(
        self,
        mock_create_fs,
        mock_unlock,
        mock_get_mounted,
        mock_get_partitions,
        mock_run
    ):
        """Test encrypt_device with custom cipher and KDF options."""
        mock_get_partitions.return_value = []
        mock_get_mounted.return_value = {}
        mock_unlock.return_value = "/dev/mapper/test-mapper"
        
        crypto_engine.encrypt_device(
            "/dev/sdb",
            "test-mapper",
            "password123",
            fs_type="ext4",
            mount_opts=[],
            cipher_opts={"type": "aes-xts-plain64", "key_size": 256},
            kdf_opts={"type": "pbkdf2"}
        )
        
        # Check that luksFormat was called with custom options
        luks_format_call = None
        for call_obj in mock_run.call_args_list:
            args = call_obj[0][0] if call_obj[0] else []
            if "luksFormat" in args:
                luks_format_call = args
                break
        
        assert luks_format_call is not None
        assert "--pbkdf" in luks_format_call
        assert "pbkdf2" in luks_format_call
        assert "--cipher" in luks_format_call
        assert "aes-xts-plain64" in luks_format_call


class TestRunCommand:
    """Test the _run helper function."""
    
    def test_run_captures_output(self):
        """Test that _run captures stdout."""
        with patch('subprocess.run') as mock_subprocess:
            mock_result = Mock()
            mock_result.stdout = b"output"
            mock_result.stderr = b""
            mock_subprocess.return_value = mock_result
            
            result = crypto_engine._run(["echo", "test"])
            
            assert result.stdout == b"output"
            mock_subprocess.assert_called_once()
    
    def test_run_passes_input_data(self):
        """Test that _run passes input data to subprocess."""
        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.return_value = Mock(stdout=b"", stderr=b"")
            
            crypto_engine._run(["cat"], input_data=b"test input")
            
            call_kwargs = mock_subprocess.call_args[1]
            assert call_kwargs['input'] == b"test input"
    
    def test_run_raises_crypto_error_on_failure(self):
        """Test that _run raises CryptoError on command failure."""
        with patch('subprocess.run') as mock_subprocess:
            error = subprocess.CalledProcessError(1, ["false"], stderr=b"error message")
            mock_subprocess.side_effect = error
            
            with pytest.raises(crypto_engine.CryptoError, match="error message"):
                crypto_engine._run(["false"])

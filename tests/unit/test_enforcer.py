"""Unit tests for enforcer module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from usb_enforcer import constants, enforcer


class TestSetBlockReadOnly:
    """Test setting block devices to read-only."""
    
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.read_text')
    def test_already_read_only(self, mock_read, mock_exists, caplog):
        """Test device already set to read-only."""
        mock_exists.return_value = True
        mock_read.return_value = "1"
        
        logger = MagicMock()
        result = enforcer.set_block_read_only("/dev/sdb1", logger)
        
        assert result is True
    
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.write_text')
    @patch('pathlib.Path.read_text')
    def test_set_read_only_success(self, mock_read, mock_write, mock_exists):
        """Test successfully setting device to read-only."""
        mock_exists.return_value = True
        mock_read.return_value = "0"
        
        logger = MagicMock()
        result = enforcer.set_block_read_only("/dev/sdb1", logger)
        
        assert result is True
        mock_write.assert_called_once_with("1")
    
    @patch('pathlib.Path.exists')
    def test_sysfs_path_missing(self, mock_exists):
        """Test when sysfs path doesn't exist."""
        mock_exists.return_value = False
        
        logger = MagicMock()
        result = enforcer.set_block_read_only("/dev/sdb1", logger)
        
        assert result is False
    
    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.read_text')
    @patch('pathlib.Path.write_text')
    @patch('subprocess.run')
    def test_fallback_to_blockdev(self, mock_run, mock_write, mock_read, mock_exists):
        """Test fallback to blockdev command."""
        mock_exists.return_value = True
        mock_read.return_value = "0"
        mock_write.side_effect = PermissionError("Permission denied")
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        logger = MagicMock()
        result = enforcer.set_block_read_only("/dev/sdb1", logger)
        
        assert result is True
        mock_run.assert_called_once()


class TestEnforcePolicy:
    """Test policy enforcement logic."""
    
    @patch('usb_enforcer.user_utils.any_active_user_in_groups')
    def test_exempted_user_bypasses_enforcement(self, mock_exempted, mock_config_file):
        """Test that exempted users bypass enforcement."""
        from usb_enforcer import config as config_module
        
        mock_exempted.return_value = (True, "user 'alice' in exempted group 'usb-exempt'")
        config = config_module.Config.load(mock_config_file)
        logger = MagicMock()
        
        device_props = {
            "ID_BUS": "usb",
            "ID_TYPE": "partition",
            "DEVTYPE": "partition",
            "ID_FS_TYPE": "ext4",
            "ID_FS_USAGE": "filesystem",
        }
        
        result = enforcer.enforce_policy(device_props, "/dev/sdb1", logger, config)
        
        assert result[constants.LOG_KEY_ACTION] == "exempt"
        assert result[constants.LOG_KEY_RESULT] == "allow"
    
    @patch('usb_enforcer.user_utils.any_active_user_in_groups')
    @patch('usb_enforcer.enforcer.set_block_read_only')
    def test_plaintext_partition_set_readonly(self, mock_setro, mock_exempted, mock_config_file):
        """Test that plaintext USB partitions are set to read-only."""
        from usb_enforcer import config as config_module
        
        mock_exempted.return_value = (False, "")
        mock_setro.return_value = True
        config = config_module.Config.load(mock_config_file)
        logger = MagicMock()
        
        device_props = {
            "ID_BUS": "usb",
            "ID_TYPE": "partition",
            "DEVTYPE": "partition",
            "ID_FS_TYPE": "ext4",
            "ID_FS_USAGE": "filesystem",
        }
        
        result = enforcer.enforce_policy(device_props, "/dev/sdb1", logger, config)
        
        assert result[constants.LOG_KEY_ACTION] == "block_rw"
        mock_setro.assert_called_once_with("/dev/sdb1", logger)
    
    @patch('usb_enforcer.user_utils.any_active_user_in_groups')
    def test_whole_disk_allowed(self, mock_exempted, mock_config_file):
        """Test that whole disk devices without filesystem are allowed."""
        from usb_enforcer import config as config_module
        
        mock_exempted.return_value = (False, "")
        config = config_module.Config.load(mock_config_file)
        logger = MagicMock()
        
        device_props = {
            "ID_BUS": "usb",
            "ID_TYPE": "disk",
            "DEVTYPE": "disk",
        }
        
        result = enforcer.enforce_policy(device_props, "/dev/sdb", logger, config)
        
        assert result[constants.LOG_KEY_ACTION] == "noop"
    
    @patch('usb_enforcer.user_utils.any_active_user_in_groups')
    def test_encrypted_device_allowed(self, mock_exempted, mock_config_file):
        """Test that encrypted devices are allowed."""
        from usb_enforcer import config as config_module
        
        mock_exempted.return_value = (False, "")
        config = config_module.Config.load(mock_config_file)
        logger = MagicMock()
        
        device_props = {
            "ID_BUS": "usb",
            "ID_TYPE": "partition",
            "DEVTYPE": "partition",
            "ID_FS_TYPE": "crypto_LUKS",
            "ID_FS_VERSION": "2",
        }
        
        result = enforcer.enforce_policy(device_props, "/dev/sdb1", logger, config)
        
        assert result[constants.LOG_KEY_ACTION] == "allow_rw"
        assert result[constants.LOG_KEY_RESULT] == "allow"
    
    @patch('usb_enforcer.user_utils.any_active_user_in_groups')
    def test_mapper_device_allowed(self, mock_exempted, mock_config_file):
        """Test that unlocked LUKS devices (mapper) are allowed."""
        from usb_enforcer import config as config_module
        
        mock_exempted.return_value = (False, "")
        config = config_module.Config.load(mock_config_file)
        logger = MagicMock()
        
        device_props = {
            "DM_UUID": "CRYPT-LUKS2-test",
            "DM_NAME": "luks-test",
            "ID_FS_TYPE": "ext4",
            "DEVTYPE": "disk",
        }
        
        result = enforcer.enforce_policy(device_props, "/dev/mapper/luks-test", logger, config)
        
        assert result[constants.LOG_KEY_ACTION] == "allow_rw"
    
    @patch('usb_enforcer.user_utils.any_active_user_in_groups')
    def test_non_usb_device_allowed(self, mock_exempted, mock_config_file):
        """Test that non-USB devices are allowed when enforce_on_usb_only is True."""
        from usb_enforcer import config as config_module
        
        mock_exempted.return_value = (False, "")
        config = config_module.Config.load(mock_config_file)
        logger = MagicMock()
        
        device_props = {
            "ID_BUS": "ata",
            "ID_TYPE": "disk",
            "DEVTYPE": "disk",
        }
        
        result = enforcer.enforce_policy(device_props, "/dev/sda", logger, config)
        
        assert result[constants.LOG_KEY_ACTION] == "noop"

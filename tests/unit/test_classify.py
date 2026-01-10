"""Unit tests for device classification."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from usb_enforcer import classify, constants


class TestDeviceClassification:
    """Test device classification logic."""
    
    def test_is_usb_storage_partition(self, mock_usb_partition_device):
        """Test USB storage partition detection."""
        assert classify.is_usb_storage(mock_usb_partition_device)
    
    def test_is_usb_storage_disk(self, mock_usb_disk_device):
        """Test USB storage disk detection."""
        assert classify.is_usb_storage(mock_usb_disk_device)
    
    def test_is_not_usb_storage(self, mock_non_usb_device):
        """Test non-USB device detection."""
        assert not classify.is_usb_storage(mock_non_usb_device)
    
    def test_is_partition(self, mock_usb_partition_device):
        """Test partition detection."""
        assert classify.is_partition(mock_usb_partition_device)
    
    def test_is_not_partition(self, mock_usb_disk_device):
        """Test disk (non-partition) detection."""
        assert not classify.is_partition(mock_usb_disk_device)
    
    def test_is_mapper(self, mock_mapper_device):
        """Test device mapper detection."""
        assert classify.is_mapper(mock_mapper_device)
    
    def test_is_not_mapper(self, mock_usb_partition_device):
        """Test non-mapper device."""
        assert not classify.is_mapper(mock_usb_partition_device)
    
    def test_classify_plaintext(self, mock_usb_partition_device):
        """Test plaintext USB device classification."""
        result = classify.classify_device(mock_usb_partition_device)
        assert result == constants.PLAINTEXT
    
    def test_classify_luks2(self, mock_luks2_device):
        """Test LUKS2 device classification."""
        result = classify.classify_device(mock_luks2_device)
        assert result == constants.LUKS2_LOCKED
    
    def test_classify_luks1(self, mock_luks1_device):
        """Test LUKS1 device classification."""
        result = classify.classify_device(mock_luks1_device)
        assert result == constants.LUKS1
    
    def test_classify_mapper(self, mock_mapper_device):
        """Test device mapper classification."""
        result = classify.classify_device(mock_mapper_device)
        assert result == constants.MAPPER
    
    def test_classify_unknown(self, mock_non_usb_device):
        """Test unknown device classification."""
        result = classify.classify_device(mock_non_usb_device)
        assert result == constants.UNKNOWN
    
    def test_classify_luks2_with_devnode(self, mock_luks2_device):
        """Test LUKS2 classification with devnode for version detection."""
        with patch('usb_enforcer.crypto_engine.luks_version') as mock_version:
            mock_version.return_value = "2"
            # Device without ID_FS_VERSION but with crypto_LUKS
            device = {
                "ID_BUS": "usb",
                "ID_TYPE": "partition",
                "DEVTYPE": "partition",
                "DEVNAME": "/dev/sdb1",
                "ID_FS_TYPE": "crypto_LUKS",
            }
            result = classify.classify_device(device, devnode="/dev/sdb1")
            assert result == constants.LUKS2_LOCKED
    
    def test_classify_case_insensitive(self):
        """Test that classification handles lowercase keys."""
        device = {
            "id_bus": "usb",
            "id_type": "partition",
            "devtype": "partition",
            "id_fs_type": "ext4",
        }
        result = classify.classify_device(device)
        assert result == constants.PLAINTEXT


class TestHelperFunctions:
    """Test helper functions."""
    
    def test_get_with_uppercase_key(self, mock_usb_partition_device):
        """Test _get function with uppercase key."""
        result = classify._get(mock_usb_partition_device, "ID_BUS")
        assert result == "usb"
    
    def test_get_with_lowercase_key(self):
        """Test _get function with lowercase key."""
        device = {"id_bus": "usb"}
        result = classify._get(device, "ID_BUS")
        assert result == "usb"
    
    def test_get_missing_key(self, mock_usb_partition_device):
        """Test _get function with missing key."""
        result = classify._get(mock_usb_partition_device, "MISSING_KEY")
        assert result is None

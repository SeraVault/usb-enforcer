"""Unit tests for udev_monitor module with mocked pyudev interactions.

These tests don't require root or actual udev events, they test logic with mocks.
"""

from __future__ import annotations

from unittest.mock import Mock, MagicMock, patch, call

import pytest

from usb_enforcer import udev_monitor


class TestStartMonitor:
    """Test udev monitor initialization and event handling."""
    
    @patch('usb_enforcer.udev_monitor.iter')
    @patch('usb_enforcer.udev_monitor.pyudev')
    def test_start_monitor_initializes_context_and_monitor(self, mock_pyudev, mock_iter):
        """Test that start_monitor initializes pyudev context and monitor."""
        mock_context = Mock()
        mock_monitor = Mock()
        mock_pyudev.Context.return_value = mock_context
        mock_pyudev.Monitor.from_netlink.return_value = mock_monitor
        
        # Make iter return empty list to exit immediately
        mock_iter.return_value = iter([])
        
        callback = Mock()
        logger = Mock()
        
        udev_monitor.start_monitor(callback, logger)
        
        # Should create context
        mock_pyudev.Context.assert_called_once()
        
        # Should create monitor from netlink
        mock_pyudev.Monitor.from_netlink.assert_called_once_with(mock_context)
        
        # Should filter by block devices
        mock_monitor.filter_by.assert_called_once_with("block")
        
        # Should log startup message
        logger.info.assert_called_once()
        assert "udev monitor" in logger.info.call_args[0][0].lower()
    
    @patch('usb_enforcer.udev_monitor.dict')
    @patch('usb_enforcer.udev_monitor.iter')
    @patch('usb_enforcer.udev_monitor.pyudev')
    def test_start_monitor_processes_device_events(self, mock_pyudev, mock_iter, mock_dict):
        """Test that start_monitor processes udev device events."""
        mock_context = Mock()
        mock_monitor = Mock()
        mock_pyudev.Context.return_value = mock_context
        mock_pyudev.Monitor.from_netlink.return_value = mock_monitor
        
        # Create mock device
        mock_device = Mock()
        mock_device.device_node = "/dev/sdb"
        mock_device.action = "add"
        
        # Mock dict() to return device properties
        mock_dict.return_value = {
            "ID_BUS": "usb",
            "ID_TYPE": "disk",
            "DEVTYPE": "disk"
        }
        
        # Make iter return one device then stop
        mock_iter.return_value = iter([mock_device])
        
        callback = Mock()
        logger = Mock()
        
        udev_monitor.start_monitor(callback, logger)
        
        # Callback should be invoked with device properties
        callback.assert_called_once()
        call_args = callback.call_args[0]
        
        # First arg: device properties dict
        device_props = call_args[0]
        assert "ID_BUS" in device_props
        assert device_props["ID_BUS"] == "usb"
        
        # Second arg: device node
        assert call_args[1] == "/dev/sdb"
        
        # Third arg: action
        assert call_args[2] == "add"
    
    @patch('usb_enforcer.udev_monitor.dict')
    @patch('usb_enforcer.udev_monitor.iter')
    @patch('usb_enforcer.udev_monitor.pyudev')
    def test_start_monitor_skips_devices_without_node(self, mock_pyudev, mock_iter, mock_dict):
        """Test that start_monitor skips devices without device_node."""
        mock_context = Mock()
        mock_monitor = Mock()
        mock_pyudev.Context.return_value = mock_context
        mock_pyudev.Monitor.from_netlink.return_value = mock_monitor
        
        # Create device with no device_node
        mock_device_no_node = Mock()
        mock_device_no_node.device_node = None
        mock_device_no_node.action = "add"
        
        # Create device with empty device_node
        mock_device_empty_node = Mock()
        mock_device_empty_node.device_node = ""
        mock_device_empty_node.action = "add"
        
        # Create valid device
        mock_device_valid = Mock()
        mock_device_valid.device_node = "/dev/sdb"
        mock_device_valid.action = "add"
        
        mock_iter.return_value = iter([
            mock_device_no_node,
            mock_device_empty_node,
            mock_device_valid
        ])
        
        mock_dict.return_value = {"ID_BUS": "usb"}
        
        callback = Mock()
        logger = Mock()
        
        udev_monitor.start_monitor(callback, logger)
        
        # Callback should only be invoked for valid device
        callback.assert_called_once()
        assert callback.call_args[0][1] == "/dev/sdb"
    
    @patch('usb_enforcer.udev_monitor.dict')
    @patch('usb_enforcer.udev_monitor.iter')
    @patch('usb_enforcer.udev_monitor.pyudev')
    def test_start_monitor_defaults_to_change_action(self, mock_pyudev, mock_iter, mock_dict):
        """Test that start_monitor defaults to 'change' action when None."""
        mock_context = Mock()
        mock_monitor = Mock()
        mock_pyudev.Context.return_value = mock_context
        mock_pyudev.Monitor.from_netlink.return_value = mock_monitor
        
        # Create device with no action
        mock_device = Mock()
        mock_device.device_node = "/dev/sdb"
        mock_device.action = None
        
        mock_iter.return_value = iter([mock_device])
        mock_dict.return_value = {"ID_BUS": "usb"}
        
        callback = Mock()
        logger = Mock()
        
        udev_monitor.start_monitor(callback, logger)
        
        # Action should default to "change"
        callback.assert_called_once()
        assert callback.call_args[0][2] == "change"
    
    @patch('usb_enforcer.udev_monitor.dict')
    @patch('usb_enforcer.udev_monitor.iter')
    @patch('usb_enforcer.udev_monitor.pyudev')
    def test_start_monitor_converts_device_to_dict(self, mock_pyudev, mock_iter, mock_dict):
        """Test that start_monitor converts device properties to dict."""
        mock_context = Mock()
        mock_monitor = Mock()
        mock_pyudev.Context.return_value = mock_context
        mock_pyudev.Monitor.from_netlink.return_value = mock_monitor
        
        # Create device
        mock_device = Mock()
        mock_device.device_node = "/dev/sdb"
        mock_device.action = "add"
        
        # Mock dict() to return all properties
        mock_dict.return_value = {
            "ID_BUS": "usb",
            "ID_TYPE": "disk",
            "ID_VENDOR": "Kingston",
            "ID_MODEL": "USB_Flash",
            "ID_SERIAL": "ABC123",
            "DEVTYPE": "disk",
            "ID_FS_TYPE": "ext4"
        }
        
        mock_iter.return_value = iter([mock_device])
        
        callback = Mock()
        logger = Mock()
        
        udev_monitor.start_monitor(callback, logger)
        
        # Check that all properties were passed
        device_props = callback.call_args[0][0]
        assert device_props["ID_BUS"] == "usb"
        assert device_props["ID_TYPE"] == "disk"
        assert device_props["ID_VENDOR"] == "Kingston"
        assert device_props["ID_MODEL"] == "USB_Flash"
        assert device_props["ID_SERIAL"] == "ABC123"
        assert device_props["DEVTYPE"] == "disk"
        assert device_props["ID_FS_TYPE"] == "ext4"
    
    @patch('usb_enforcer.udev_monitor.iter')
    @patch('usb_enforcer.udev_monitor.pyudev')
    def test_start_monitor_logs_startup_message(self, mock_pyudev, mock_iter):
        """Test that start_monitor logs appropriate startup message."""
        mock_context = Mock()
        mock_monitor = Mock()
        mock_pyudev.Context.return_value = mock_context
        mock_pyudev.Monitor.from_netlink.return_value = mock_monitor
        mock_iter.return_value = iter([])
        
        callback = Mock()
        logger = Mock()
        
        udev_monitor.start_monitor(callback, logger)
        
        # Should log startup message
        logger.info.assert_called_once()
        log_message = logger.info.call_args[0][0]
        assert "Starting udev monitor" in log_message
        assert "block devices" in log_message
    
    @patch('usb_enforcer.udev_monitor.iter')
    @patch('usb_enforcer.udev_monitor.pyudev')
    def test_start_monitor_filter_by_block_devices(self, mock_pyudev, mock_iter):
        """Test that monitor is filtered to only block devices."""
        mock_context = Mock()
        mock_monitor = Mock()
        mock_pyudev.Context.return_value = mock_context
        mock_pyudev.Monitor.from_netlink.return_value = mock_monitor
        mock_iter.return_value = iter([])
        
        callback = Mock()
        logger = Mock()
        
        udev_monitor.start_monitor(callback, logger)
        
        # Should filter by "block" subsystem
        mock_monitor.filter_by.assert_called_once_with("block")

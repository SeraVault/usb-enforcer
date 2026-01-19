"""
Integration tests for daemon's unformatted drive detection.
These tests verify that the daemon correctly detects unformatted drives
and emits appropriate events based on user exemption status.
"""
import pytest
import subprocess
import time
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from usb_enforcer import daemon, config as config_module


class TestDaemonUnformattedDetection:
    """Test daemon detection and handling of unformatted drives."""

    @pytest.fixture
    def unformatted_loop_device(self, temp_dir):
        """Create an unformatted loop device for testing."""
        # Create a 100MB empty file
        device_file = Path(temp_dir) / "unformatted.img"
        subprocess.run(
            ["dd", "if=/dev/zero", f"of={device_file}", "bs=1M", "count=100"],
            check=True,
            capture_output=True
        )
        
        # Attach to loop device
        result = subprocess.run(
            ["losetup", "-f", "--show", str(device_file)],
            capture_output=True,
            text=True,
            check=True
        )
        loop_device = result.stdout.strip()
        
        yield loop_device
        
        # Cleanup
        try:
            subprocess.run(["losetup", "-d", loop_device], check=False, capture_output=True)
        except Exception:
            pass

    @pytest.fixture
    def daemon_with_mock_dbus(self, temp_dir):
        """Create a daemon instance with mocked DBus service."""
        d = daemon.Daemon()
        d.config.base_mount_dir = temp_dir
        d.config.content_scanning.enabled = False  # Disable for simplicity
        
        # Mock the DBus service to capture events
        mock_dbus = Mock()
        mock_dbus.emit_event = Mock()
        d.dbus_service = mock_dbus
        
        yield d
        
        # Cleanup
        try:
            d.stop()
        except Exception:
            pass

    def test_unformatted_drive_detection(self, unformatted_loop_device, daemon_with_mock_dbus):
        """Test that daemon detects an unformatted drive and emits event."""
        d = daemon_with_mock_dbus
        device_path = unformatted_loop_device
        
        # Create mock udev context with unformatted device properties
        device_props = {
            'DEVNAME': device_path,
            'DEVTYPE': 'disk',
            'SUBSYSTEM': 'block',
            'ID_BUS': 'usb',
            'ID_TYPE': 'disk',
            # No ID_FS_TYPE - indicates unformatted
        }
        
        # Mock console user exemption check to return (False, None) (non-exempted user)
        with patch('usb_enforcer.encryption.user_utils.any_active_user_in_groups', return_value=(False, None)):
            # Handle the device
            d.handle_device(device_props, device_path, 'add')
        
        # Verify event was emitted
        assert d.dbus_service.emit_event.called
        
        # Get all emitted events (should include unformatted_drive)
        calls = d.dbus_service.emit_event.call_args_list
        events = [call[0][0] for call in calls]
        
        # Find the unformatted_drive event
        unformatted_events = [e for e in events if e.get('USB_EE_EVENT') == 'unformatted_drive']
        assert len(unformatted_events) > 0, "Expected unformatted_drive event to be emitted"
        
        event_data = unformatted_events[0]
        
        # Verify event structure
        assert device_path in event_data.get('DEVNODE', '')
        assert event_data.get('preferred_encryption') == d.config.default_encryption_type
        assert event_data.get('preferred_filesystem') == d.config.filesystem_type

    def test_unformatted_drive_exempted_user(self, unformatted_loop_device, daemon_with_mock_dbus):
        """Test unformatted drive detection for exempted user shows format option."""
        d = daemon_with_mock_dbus
        device_path = unformatted_loop_device
        
        # Set exempted groups in config
        d.config.exempted_groups = ['exempt-group']
        
        device_props = {
            'DEVNAME': device_path,
            'DEVTYPE': 'disk',
            'SUBSYSTEM': 'block',
            'ID_BUS': 'usb',
            'ID_TYPE': 'disk',
            # No ID_FS_TYPE
        }
        
        # Mock console user exemption check to return (True, 'reason') (exempted user)
        with patch('usb_enforcer.encryption.user_utils.any_active_user_in_groups', return_value=(True, 'exempt-group')):
            d.handle_device(device_props, device_path, 'add')
        
        # Verify event was emitted with ACTION=format_prompt
        assert d.dbus_service.emit_event.called
        calls = d.dbus_service.emit_event.call_args_list
        events = [call[0][0] for call in calls]
        
        unformatted_events = [e for e in events if e.get('USB_EE_EVENT') == 'unformatted_drive']
        assert len(unformatted_events) > 0
        event_data = unformatted_events[0]
        
        assert event_data.get('ACTION') == 'format_prompt'

    def test_unformatted_drive_non_exempted_user(self, unformatted_loop_device, daemon_with_mock_dbus):
        """Test unformatted drive detection for non-exempted user shows encrypt option."""
        d = daemon_with_mock_dbus
        device_path = unformatted_loop_device
        
        d.config.exempted_groups = ['exempt-group']
        
        device_props = {
            'DEVNAME': device_path,
            'DEVTYPE': 'disk',
            'SUBSYSTEM': 'block',
            'ID_BUS': 'usb',
            'ID_TYPE': 'disk',
            # No ID_FS_TYPE
        }
        
        # Mock console user exemption check to return (False, None)
        with patch('usb_enforcer.encryption.user_utils.any_active_user_in_groups', return_value=(False, None)):
            d.handle_device(device_props, device_path, 'add')
        
        # Verify event was emitted with ACTION=encrypt_prompt
        assert d.dbus_service.emit_event.called
        calls = d.dbus_service.emit_event.call_args_list
        events = [call[0][0] for call in calls]
        
        unformatted_events = [e for e in events if e.get('USB_EE_EVENT') == 'unformatted_drive']
        assert len(unformatted_events) > 0
        event_data = unformatted_events[0]
        
        assert event_data.get('ACTION') == 'encrypt_prompt'

    def test_formatted_drive_no_unformatted_event(self, temp_dir, daemon_with_mock_dbus):
        """Test that formatted drives don't trigger unformatted_drive event."""
        d = daemon_with_mock_dbus
        
        # Create and format a loop device
        device_file = Path(temp_dir) / "formatted.img"
        subprocess.run(
            ["dd", "if=/dev/zero", f"of={device_file}", "bs=1M", "count=100"],
            check=True,
            capture_output=True
        )
        
        result = subprocess.run(
            ["losetup", "-f", "--show", str(device_file)],
            capture_output=True,
            text=True,
            check=True
        )
        loop_device = result.stdout.strip()
        
        try:
            # Format with ext4
            subprocess.run(
                ["mkfs.ext4", "-F", loop_device],
                check=True,
                capture_output=True
            )
            
            # Wait for udev
            time.sleep(0.5)
            
            # Create mock env with ID_FS_TYPE (indicates formatted)
            device_props = {
                'DEVNAME': loop_device,
                'DEVTYPE': 'disk',
                'SUBSYSTEM': 'block',
                'ID_BUS': 'usb',
                'ID_FS_TYPE': 'ext4',
            }
            
            # Handle the device
            d.handle_device(device_props, loop_device, 'add')
            
            # Verify no unformatted_drive event was emitted
            if d.dbus_service.emit_event.called:
                call_args = d.dbus_service.emit_event.call_args
                event_data = call_args[0][0] if call_args else {}
                assert event_data.get('USB_EE_EVENT') != 'unformatted_drive'
                
        finally:
            subprocess.run(["losetup", "-d", loop_device], check=False, capture_output=True)

    def test_config_preferences_in_event(self, unformatted_loop_device, daemon_with_mock_dbus):
        """Test that config preferences are included in the event."""
        d = daemon_with_mock_dbus
        
        # Set specific config values
        d.config.default_encryption_type = "veracrypt"
        d.config.filesystem_type = "exfat"
        
        device_props = {
            'DEVNAME': unformatted_loop_device,
            'DEVTYPE': 'disk',
            'SUBSYSTEM': 'block',
            'ID_BUS': 'usb',
            'ID_TYPE': 'disk',
        }
        
        with patch('usb_enforcer.encryption.user_utils.any_active_user_in_groups', return_value=(False, None)):
            d.handle_device(device_props, unformatted_loop_device, 'add')
        
        # Verify config values in event
        calls = d.dbus_service.emit_event.call_args_list
        events = [call[0][0] for call in calls]
        
        unformatted_events = [e for e in events if e.get('USB_EE_EVENT') == 'unformatted_drive']
        assert len(unformatted_events) > 0
        event_data = unformatted_events[0]
        
        assert event_data.get('preferred_encryption') == 'veracrypt'
        assert event_data.get('preferred_filesystem') == 'exfat'


class TestUnformattedDriveRealWorldScenarios:
    """Real-world scenarios with actual loop devices."""

    @pytest.fixture
    def real_unformatted_device(self, temp_dir):
        """Create a real unformatted loop device."""
        device_file = Path(temp_dir) / "real_unformatted.img"
        subprocess.run(
            ["dd", "if=/dev/zero", f"of={device_file}", "bs=1M", "count=50"],
            check=True,
            capture_output=True
        )
        
        result = subprocess.run(
            ["losetup", "-f", "--show", str(device_file)],
            capture_output=True,
            text=True,
            check=True
        )
        loop_device = result.stdout.strip()
        
        yield loop_device
        
        try:
            subprocess.run(["losetup", "-d", loop_device], check=False, capture_output=True)
        except Exception:
            pass

    def test_real_unformatted_device_properties(self, real_unformatted_device):
        """Test that a real unformatted device has expected properties."""
        device = real_unformatted_device
        
        # Check that blkid shows no filesystem
        result = subprocess.run(
            ["blkid", device],
            capture_output=True,
            text=True
        )
        
        # blkid returns exit code 2 for devices with no filesystem
        assert result.returncode == 2 or "TYPE" not in result.stdout
        
        # Verify device exists and is a block device
        assert os.path.exists(device)
        stat_result = os.stat(device)
        import stat
        assert stat.S_ISBLK(stat_result.st_mode)

    def test_daemon_with_real_unformatted_device(self, real_unformatted_device, temp_dir):
        """Integration test with real unformatted device through daemon."""
        d = daemon.Daemon()
        d.config.base_mount_dir = temp_dir
        d.config.content_scanning.enabled = False
        d.config.default_encryption_type = "luks2"
        d.config.filesystem_type = "ext4"
        
        # Mock DBus
        mock_dbus = Mock()
        mock_dbus.emit_event = Mock()
        d.dbus_service = mock_dbus
        
        # Simulate device properties from udev
        device_props = {
            'DEVNAME': real_unformatted_device,
            'DEVTYPE': 'disk',
            'SUBSYSTEM': 'block',
            'ID_BUS': 'usb',
            'ID_TYPE': 'disk',
            'MAJOR': '7',
            'MINOR': '0',
        }
        
        with patch('usb_enforcer.encryption.user_utils.any_active_user_in_groups', return_value=(False, None)):
            d.handle_device(device_props, real_unformatted_device, 'add')
        
        # Verify event emission
        assert mock_dbus.emit_event.called
        calls = mock_dbus.emit_event.call_args_list
        events = [call[0][0] for call in calls]
        
        unformatted_events = [e for e in events if e.get('USB_EE_EVENT') == 'unformatted_drive']
        assert len(unformatted_events) > 0
        event_data = unformatted_events[0]
        
        assert event_data.get('ACTION') == 'encrypt_prompt'
        assert event_data.get('preferred_encryption') == 'luks2'
        assert event_data.get('preferred_filesystem') == 'ext4'

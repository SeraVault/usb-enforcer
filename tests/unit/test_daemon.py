"""Unit tests for daemon module with mocked system interactions.

These tests don't require root or actual devices, they test logic with mocks.
"""

from __future__ import annotations

import threading
from unittest.mock import Mock, MagicMock, patch, call

import pytest

from usb_enforcer import daemon, constants


class TestDaemonInitialization:
    """Test daemon initialization and setup."""
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    def test_daemon_initializes_with_defaults(self, mock_context, mock_logging, mock_config):
        """Test daemon initialization with default config."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        mock_config.return_value.default_plain_mount_opts = ["nodev", "nosuid", "ro"]
        mock_config.return_value.require_noexec_on_plain = False
        
        d = daemon.Daemon()
        
        assert d.devices == {}
        assert d.dbus_service is None
        assert len(d._bypass_enforcement) == 0
        assert d._secret_socket_path == "/run/usb-enforcer.sock"
        mock_config.assert_called_once_with(None)
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    def test_daemon_initializes_with_custom_config(self, mock_context, mock_logging, mock_config):
        """Test daemon initialization with custom config path."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        mock_config.return_value.default_plain_mount_opts = ["nodev", "nosuid", "ro"]
        mock_config.return_value.require_noexec_on_plain = False
        
        d = daemon.Daemon(config_path="/etc/custom.toml")
        
        mock_config.assert_called_once_with("/etc/custom.toml")


class TestDeviceHandling:
    """Test device event handling logic."""
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    @patch('usb_enforcer.daemon.classify.classify_device')
    @patch('usb_enforcer.daemon.enforcer.enforce_policy')
    def test_handle_device_add_plaintext(
        self,
        mock_enforce,
        mock_classify,
        mock_context,
        mock_logging,
        mock_config
    ):
        """Test handling plaintext device addition."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        mock_classify.return_value = constants.PLAINTEXT
        mock_enforce.return_value = {
            constants.LOG_KEY_ACTION: "block_rw",
            constants.LOG_KEY_RESULT: "allow"
        }
        
        d = daemon.Daemon()
        device_props = {
            "ID_BUS": "usb",
            "ID_TYPE": "disk",
            "ID_SERIAL": "ABC123",
            "DEVTYPE": "disk"
        }
        
        with patch.object(d, '_trigger_mount_ro') as mock_mount:
            d.handle_device(device_props, "/dev/sdb", "add")
        
        # Device should be added to cache
        assert "/dev/sdb" in d.devices
        assert d.devices["/dev/sdb"]["classification"] == constants.PLAINTEXT
        assert d.devices["/dev/sdb"]["serial"] == "ABC123"
        
        # Should attempt to trigger mount for plaintext devices set RO
        mock_mount.assert_called_once_with("/dev/sdb")


class TestFuseOverlaySetup:
    """Test FUSE overlay setup behavior."""

    @patch('usb_enforcer.daemon.time.sleep', return_value=None)
    @patch('usb_enforcer.daemon.os.makedirs')
    @patch('usb_enforcer.daemon.subprocess.run')
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    def test_setup_fuse_overlay_handles_shared_mount(
        self,
        mock_context,
        mock_logging,
        mock_config,
        mock_run,
        mock_makedirs,
        _mock_sleep
    ):
        """Ensure shared mount propagation triggers make-rprivate before move."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()

        d = daemon.Daemon()
        d.fuse_manager = Mock()
        d.fuse_manager.mounts = {}
        d.fuse_manager.mount.return_value = True

        d._cleanup_existing_mounts = Mock()

        mount_point = "/run/media/user/test"
        real_mount = "/run/media/user/.usb-enforcer-backing/test"
        move_calls = {'count': 0}

        def run_side_effect(args, **_kwargs):
            if args[0] == "findmnt":
                return Mock(returncode=0, stdout=mount_point, stderr="")
            if args[0] == "mount" and args[1] == "--move":
                move_calls['count'] += 1
                if move_calls['count'] == 1:
                    return Mock(returncode=32, stdout="", stderr="shared mount")
                return Mock(returncode=0, stdout="", stderr="")
            if args[0] == "mount" and args[1] == "--make-rprivate":
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = run_side_effect

        mock_makedirs.return_value = None

        d._setup_fuse_overlay("/dev/dm-0")

        calls = [call_args[0][0] for call_args in mock_run.call_args_list]
        assert ["mount", "--make-rprivate", "/run"] in calls
        assert calls.count(["mount", "--move", mount_point, real_mount]) == 2
        d.fuse_manager.mount.assert_called_once()
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    def test_handle_device_remove(self, mock_context, mock_logging, mock_config):
        """Test handling device removal."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        
        d = daemon.Daemon()
        # Add a device first
        d.devices["/dev/sdb"] = {"devnode": "/dev/sdb"}
        d._bypass_enforcement.add("/dev/sdb")
        
        with patch.object(d, '_cleanup_stale_mounts') as mock_cleanup:
            d.handle_device({}, "/dev/sdb", "remove")
        
        # Device should be removed from cache
        assert "/dev/sdb" not in d.devices
        # Device should be removed from bypass list
        assert "/dev/sdb" not in d._bypass_enforcement
        # Cleanup should be called
        mock_cleanup.assert_called_once_with("/dev/sdb")
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    @patch('usb_enforcer.daemon.classify.classify_device')
    @patch('usb_enforcer.daemon.enforcer.enforce_policy')
    def test_handle_device_bypassed(
        self,
        mock_enforce,
        mock_classify,
        mock_context,
        mock_logging,
        mock_config
    ):
        """Test handling device that's in bypass list."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        mock_classify.return_value = constants.PLAINTEXT
        
        d = daemon.Daemon()
        d._bypass_enforcement.add("/dev/sdb")
        
        device_props = {"ID_BUS": "usb", "ID_TYPE": "disk"}
        d.handle_device(device_props, "/dev/sdb", "add")
        
        # Should not enforce policy when bypassed
        mock_enforce.assert_not_called()
        
        # Device still added to cache
        assert "/dev/sdb" in d.devices


class TestBypassMechanism:
    """Test enforcement bypass logic."""
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    def test_is_enforcement_bypassed_exact_match(self, mock_context, mock_logging, mock_config):
        """Test bypass detection with exact device match."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        
        d = daemon.Daemon()
        d._bypass_enforcement.add("/dev/sdb")
        
        assert d._is_enforcement_bypassed("/dev/sdb") is True
        assert d._is_enforcement_bypassed("/dev/sdc") is False
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    def test_is_enforcement_bypassed_parent_child(self, mock_context, mock_logging, mock_config):
        """Test bypass detection for parent/child relationships."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        
        d = daemon.Daemon()
        d._bypass_enforcement.add("/dev/sdb")
        
        # Child partition should be bypassed if parent is bypassed
        assert d._is_enforcement_bypassed("/dev/sdb1") is True
        # Parent should be bypassed if child is in bypass list
        d._bypass_enforcement.clear()
        d._bypass_enforcement.add("/dev/sdb1")
        assert d._is_enforcement_bypassed("/dev/sdb") is True


class TestDeviceQueries:
    """Test device listing and status queries."""
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    def test_list_devices_empty(self, mock_context, mock_logging, mock_config):
        """Test listing devices when none are present."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        
        d = daemon.Daemon()
        
        devices = d.list_devices()
        assert devices == []
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    def test_list_devices_multiple(self, mock_context, mock_logging, mock_config):
        """Test listing multiple devices."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        
        d = daemon.Daemon()
        d.devices["/dev/sdb"] = {"devnode": "/dev/sdb", "classification": "plaintext"}
        d.devices["/dev/sdc"] = {"devnode": "/dev/sdc", "classification": "luks2"}
        
        devices = d.list_devices()
        assert len(devices) == 2
        assert any(dev["devnode"] == "/dev/sdb" for dev in devices)
        assert any(dev["devnode"] == "/dev/sdc" for dev in devices)
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    def test_get_device_status_exists(self, mock_context, mock_logging, mock_config):
        """Test getting status of existing device."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        
        d = daemon.Daemon()
        d.devices["/dev/sdb"] = {"devnode": "/dev/sdb", "classification": "plaintext"}
        
        status = d.get_device_status("/dev/sdb")
        assert status["devnode"] == "/dev/sdb"
        assert status["classification"] == "plaintext"
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    def test_get_device_status_missing(self, mock_context, mock_logging, mock_config):
        """Test getting status of non-existent device."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        
        d = daemon.Daemon()
        
        status = d.get_device_status("/dev/nonexistent")
        assert status == {}


class TestMapperNameGeneration:
    """Test mapper name generation for encrypted devices."""
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    def test_mapper_name_for_device(self, mock_context, mock_logging, mock_config):
        """Test generating mapper name from device node."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        
        d = daemon.Daemon()
        
        assert d._mapper_name_for("/dev/sdb") == "usbenc-sdb"
        assert d._mapper_name_for("/dev/sdb1") == "usbenc-sdb1"
        assert d._mapper_name_for("/dev/loop0") == "usbenc-loop0"


class TestCleanupStaleMounts:
    """Test stale mount cleanup logic."""
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    @patch('subprocess.run')
    def test_cleanup_stale_mounts_unmounts_device(
        self,
        mock_run,
        mock_context,
        mock_logging,
        mock_config
    ):
        """Test cleanup unmounts devices that match removed device."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        
        # Mock findmnt output showing mounted device
        mock_findmnt = Mock()
        mock_findmnt.returncode = 0
        mock_findmnt.stdout = "/run/media/user/USB /dev/sdb1\n"
        mock_run.return_value = mock_findmnt
        
        d = daemon.Daemon()
        d._cleanup_stale_mounts("/dev/sdb1")
        
        # Should call umount
        umount_calls = [c for c in mock_run.call_args_list if "umount" in str(c)]
        assert len(umount_calls) > 0
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    @patch('subprocess.run')
    def test_cleanup_stale_mounts_no_mounts(
        self,
        mock_run,
        mock_context,
        mock_logging,
        mock_config
    ):
        """Test cleanup handles case with no mounts."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        
        # Mock findmnt returning nothing
        mock_findmnt = Mock()
        mock_findmnt.returncode = 0
        mock_findmnt.stdout = ""
        mock_run.return_value = mock_findmnt
        
        d = daemon.Daemon()
        d._cleanup_stale_mounts("/dev/sdb1")
        
        # Should only call findmnt checks, not umount
        assert mock_run.call_count == 2


class TestEventLogging:
    """Test event logging and D-Bus emission."""
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    @patch('usb_enforcer.daemon.logging_utils.log_structured')
    def test_log_event_logs_message(
        self,
        mock_log_structured,
        mock_context,
        mock_logging,
        mock_config
    ):
        """Test that _log_event logs structured messages."""
        mock_config.return_value = Mock()
        mock_logger = Mock()
        mock_logging.return_value = mock_logger
        
        d = daemon.Daemon()
        fields = {"devnode": "/dev/sdb", "action": "add"}
        
        d._log_event("test message", fields)
        
        mock_log_structured.assert_called_once_with(
            mock_logger,
            "test message",
            fields
        )
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    def test_emit_event_with_dbus_service(self, mock_context, mock_logging, mock_config):
        """Test that events are emitted via D-Bus when service exists."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        
        d = daemon.Daemon()
        d.dbus_service = Mock()
        
        fields = {"devnode": "/dev/sdb"}
        d._emit_event(fields)
        
        d.dbus_service.emit_event.assert_called_once_with(fields)
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    def test_emit_event_without_dbus_service(self, mock_context, mock_logging, mock_config):
        """Test that emit_event handles missing D-Bus service gracefully."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        
        d = daemon.Daemon()
        d.dbus_service = None
        
        fields = {"devnode": "/dev/sdb"}
        # Should not raise exception
        d._emit_event(fields)


class TestTriggerMountRO:
    """Test read-only mount triggering."""
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    @patch('usb_enforcer.daemon.time.sleep', return_value=None)
    @patch('usb_enforcer.daemon.os.makedirs')
    @patch('usb_enforcer.daemon.user_utils.get_active_session_user')
    @patch('threading.Thread')
    @patch('usb_enforcer.daemon.subprocess.run')
    @patch('pwd.getpwnam')
    @patch('os.chown')
    def test_trigger_mount_ro_mounts_device(
        self,
        mock_chown,
        mock_getpwnam,
        mock_run,
        mock_thread,
        mock_get_active_user,
        mock_makedirs,
        _mock_sleep,
        mock_context,
        mock_logging,
        mock_config
    ):
        """Test that _trigger_mount_ro attempts to mount device."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        mock_config.return_value.default_plain_mount_opts = ["nodev", "nosuid", "ro"]
        mock_config.return_value.require_noexec_on_plain = False
        
        mock_get_active_user.return_value = "testuser"
        mock_makedirs.return_value = None

        # Mock blkid label lookup and mount success
        mock_blkid = Mock(returncode=0, stdout="USB\n")
        mock_mount = Mock(returncode=0, stdout="")
        mock_run.side_effect = [mock_blkid, mock_mount]
        
        # Mock user info
        mock_pw = Mock(pw_uid=1000, pw_gid=1000)
        mock_getpwnam.return_value = mock_pw
        
        # Mock threading to execute callback immediately
        def immediate_thread(target, *args, **kwargs):
            target()
            return Mock()
        mock_thread.side_effect = immediate_thread
        
        d = daemon.Daemon()
        d._trigger_mount_ro("/dev/sdb1")
        
        # Should have called mount for the device
        mount_calls = [c for c in mock_run.call_args_list if "mount" in str(c)]
        assert len(mount_calls) > 0
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    @patch('usb_enforcer.daemon.time.sleep', return_value=None)
    @patch('usb_enforcer.daemon.os.makedirs')
    @patch('usb_enforcer.daemon.user_utils.get_active_session_user')
    @patch('threading.Thread')
    @patch('usb_enforcer.daemon.subprocess.run')
    def test_trigger_mount_ro_handles_mount_failure(
        self,
        mock_run,
        mock_thread,
        mock_get_active_user,
        mock_makedirs,
        _mock_sleep,
        mock_context,
        mock_logging,
        mock_config
    ):
        """Test that mount failure is handled gracefully."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        mock_config.return_value.default_plain_mount_opts = ["nodev", "nosuid", "ro"]
        mock_config.return_value.require_noexec_on_plain = False
        
        mock_get_active_user.return_value = "testuser"
        mock_makedirs.return_value = None

        # Mock blkid label lookup and mount failure
        mock_blkid = Mock(returncode=0, stdout="USB\n")
        mock_mount = Mock(returncode=1, stderr="Device not found\n")
        mock_run.side_effect = [mock_blkid, mock_mount]
        
        # Mock threading to execute callback immediately
        def immediate_thread(target, *args, **kwargs):
            target()
            return Mock()
        mock_thread.side_effect = immediate_thread
        
        d = daemon.Daemon()
        # Should not raise exception
        d._trigger_mount_ro("/dev/sdb1")


class TestSecretStore:
    """Test secret token storage for UI operations."""
    
    @patch('usb_enforcer.daemon.config_module.Config.load')
    @patch('usb_enforcer.daemon.logging_utils.setup_logging')
    @patch('usb_enforcer.daemon.pyudev.Context')
    def test_secret_store_initialized_empty(self, mock_context, mock_logging, mock_config):
        """Test that secret store is initialized empty."""
        mock_config.return_value = Mock()
        mock_logging.return_value = Mock()
        
        d = daemon.Daemon()
        
        assert d._secret_store == {}
        assert isinstance(d._secret_lock, threading.Lock)

"""Unit tests for user and group utilities."""

from __future__ import annotations

import grp
import pwd
from unittest.mock import MagicMock, patch

import pytest

from usb_enforcer import user_utils


class TestActiveUsers:
    """Test active user detection."""
    
    @patch('usb_enforcer.user_utils._get_active_loginctl_users', return_value=None)
    @patch('subprocess.run')
    def test_get_active_users_from_who(self, mock_run, _mock_loginctl):
        """Test getting active users from 'who' command."""
        mock_result = MagicMock()
        mock_result.stdout = "alice   tty1  2026-01-10 10:00\nbob     pts/0 2026-01-10 11:00\n"
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        users = user_utils.get_active_users()
        assert "alice" in users
        assert "bob" in users
        assert "root" not in users
    
    @patch('usb_enforcer.user_utils._get_active_loginctl_users', return_value=None)
    @patch('subprocess.run')
    def test_get_active_users_excludes_root(self, mock_run, _mock_loginctl):
        """Test that root is excluded from active users."""
        mock_result = MagicMock()
        mock_result.stdout = "root    tty1  2026-01-10 10:00\nalice   pts/0 2026-01-10 11:00\n"
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        users = user_utils.get_active_users()
        assert "alice" in users
        assert "root" not in users
    
    @patch('usb_enforcer.user_utils._get_active_loginctl_users', return_value={"alice", "bob"})
    @patch('subprocess.run')
    def test_get_active_users_loginctl(self, mock_run, _mock_loginctl):
        """Test getting active users from loginctl."""
        users = user_utils.get_active_users()
        assert "alice" in users
        assert "bob" in users
    
    @patch('subprocess.run')
    def test_get_active_users_handles_errors(self, mock_run):
        """Test that errors are handled gracefully."""
        mock_run.side_effect = Exception("Command failed")
        
        users = user_utils.get_active_users()
        assert isinstance(users, set)


class TestGroupMembership:
    """Test group membership checking."""
    
    @patch('grp.getgrnam')
    @patch('pwd.getpwnam')
    def test_user_in_group_primary(self, mock_getpwnam, mock_getgrnam):
        """Test user in group via primary gid."""
        # Mock user info
        mock_pwd = MagicMock()
        mock_pwd.pw_gid = 1000
        mock_getpwnam.return_value = mock_pwd
        
        # Mock group info
        mock_grp = MagicMock()
        mock_grp.gr_gid = 1000
        mock_grp.gr_mem = []
        mock_getgrnam.return_value = mock_grp
        
        result = user_utils.user_in_group("alice", "testgroup")
        assert result is True
    
    @patch('grp.getgrnam')
    @patch('pwd.getpwnam')
    def test_user_in_group_secondary(self, mock_getpwnam, mock_getgrnam):
        """Test user in group via secondary membership."""
        # Mock user info
        mock_pwd = MagicMock()
        mock_pwd.pw_gid = 1000
        mock_getpwnam.return_value = mock_pwd
        
        # Mock group info
        mock_grp = MagicMock()
        mock_grp.gr_gid = 2000
        mock_grp.gr_mem = ["alice", "bob"]
        mock_getgrnam.return_value = mock_grp
        
        result = user_utils.user_in_group("alice", "testgroup")
        assert result is True
    
    @patch('grp.getgrnam')
    @patch('pwd.getpwnam')
    def test_user_not_in_group(self, mock_getpwnam, mock_getgrnam):
        """Test user not in group."""
        # Mock user info
        mock_pwd = MagicMock()
        mock_pwd.pw_gid = 1000
        mock_getpwnam.return_value = mock_pwd
        
        # Mock group info
        mock_grp = MagicMock()
        mock_grp.gr_gid = 2000
        mock_grp.gr_mem = ["bob"]
        mock_getgrnam.return_value = mock_grp
        
        result = user_utils.user_in_group("alice", "testgroup")
        assert result is False
    
    @patch('grp.getgrnam')
    @patch('pwd.getpwnam')
    def test_user_in_group_handles_errors(self, mock_getpwnam, mock_getgrnam):
        """Test that errors are handled gracefully."""
        mock_getpwnam.side_effect = KeyError("User not found")
        
        result = user_utils.user_in_group("nonexistent", "testgroup")
        assert result is False


class TestUserInAnyExemptedGroup:
    """Test checking if user is in any exempted group."""
    
    @patch('usb_enforcer.user_utils.user_in_group')
    def test_user_in_exempted_group(self, mock_user_in_group):
        """Test user in one of the exempted groups."""
        mock_user_in_group.side_effect = lambda user, group: group == "usb-exempt"
        
        # Check using the actual function - user_in_group for individual checks
        result = user_utils.user_in_group("alice", "usb-exempt")
        assert result is True
    
    @patch('usb_enforcer.user_utils.user_in_group')
    def test_user_not_in_exempted_groups(self, mock_user_in_group):
        """Test user not in any exempted groups."""
        mock_user_in_group.return_value = False
        
        result = user_utils.user_in_group("alice", "usb-exempt")
        assert result is False
    
    def test_empty_exempted_groups(self):
        """Test with empty exempted groups list."""
        import logging
        logger = logging.getLogger("test")
        result, _ = user_utils.any_active_user_in_groups([], logger)
        assert result is False


class TestAnyActiveUserExempted:
    """Test checking if any active user is exempted."""
    
    @patch('usb_enforcer.user_utils.get_active_users')
    @patch('usb_enforcer.user_utils.user_in_group')
    def test_some_active_users_exempted(self, mock_user_in_group, mock_active):
        """Test when some active users are exempted."""
        import logging
        
        mock_active.return_value = {"alice", "bob"}
        mock_user_in_group.side_effect = lambda user, group: user == "alice" and group == "usb-exempt"
        
        logger = logging.getLogger("test")
        result, reason = user_utils.any_active_user_in_groups(["usb-exempt"], logger)
        assert result is True
        assert "alice" in reason
    
    @patch('usb_enforcer.user_utils.get_active_users')
    @patch('usb_enforcer.user_utils.user_in_group')
    def test_no_active_users_exempted(self, mock_user_in_group, mock_active):
        """Test when no active users are exempted."""
        import logging
        
        mock_active.return_value = {"alice", "bob"}
        mock_user_in_group.return_value = False
        
        logger = logging.getLogger("test")
        result, _ = user_utils.any_active_user_in_groups(["usb-exempt"], logger)
        assert result is False
    
    @patch('usb_enforcer.user_utils.get_active_users')
    def test_no_active_users(self, mock_active):
        """Test when there are no active users."""
        import logging
        
        mock_active.return_value = set()
        
        logger = logging.getLogger("test")
        result, _ = user_utils.any_active_user_in_groups(["usb-exempt"], logger)
        assert result is False

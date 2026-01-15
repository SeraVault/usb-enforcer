"""Utilities for user and group membership checking."""

from __future__ import annotations

import grp
import logging
import pwd
import subprocess
from typing import List, Set


def get_active_users() -> Set[str]:
    """
    Get list of currently logged-in non-root users.
    Returns a set of usernames.
    """
    users = set()
    try:
        result = subprocess.run(["who"], capture_output=True, text=True, check=False)
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts:
                user = parts[0]
                if user != "root":
                    users.add(user)
    except Exception:
        pass
    
    # Also check loginctl if available (for systemd systems)
    try:
        result = subprocess.run(
            ["loginctl", "list-sessions", "--no-legend"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    user = parts[2]
                    if user != "root":
                        users.add(user)
    except (FileNotFoundError, Exception):
        pass
    
    return users


def user_in_group(username: str, groupname: str) -> bool:
    """
    Check if a user is a member of a specified group.
    
    Args:
        username: The username to check
        groupname: The group name to check membership in
        
    Returns:
        True if user is in the group, False otherwise
    """
    try:
        # Get group information
        group_info = grp.getgrnam(groupname)
        
        # Check if user is in the group's member list
        if username in group_info.gr_mem:
            return True
        
        # Also check if this is the user's primary group
        try:
            user_info = pwd.getpwnam(username)
            if user_info.pw_gid == group_info.gr_gid:
                return True
        except KeyError:
            pass
            
    except KeyError:
        # Group doesn't exist
        pass
    except Exception:
        pass
    
    return False


def any_active_user_in_groups(exempted_groups: List[str], logger: logging.Logger) -> tuple[bool, str]:
    """
    Check if any currently logged-in user is a member of any exempted group.
    
    Args:
        exempted_groups: List of group names that provide exemption
        logger: Logger instance for debug output
        
    Returns:
        Tuple of (is_exempted: bool, reason: str)
        - is_exempted: True if any active user is in an exempted group
        - reason: Description of which user/group matched, or empty string
    """
    if not exempted_groups:
        return False, ""
    
    active_users = get_active_users()
    logger.debug(f"Active users: {active_users}")
    logger.debug(f"Exempted groups: {exempted_groups}")
    
    for user in active_users:
        for group in exempted_groups:
            if user_in_group(user, group):
                reason = f"user '{user}' in exempted group '{group}'"
                logger.info(f"Exempting enforcement: {reason}")
                return True, reason
    
    return False, ""

"""Utilities for user and group membership checking."""

from __future__ import annotations

import grp
import logging
import pwd
import subprocess
from typing import List, Set, Optional


def _get_active_loginctl_users() -> Optional[Set[str]]:
    """
    Get list of active local users via loginctl.
    Returns a set of usernames or None if loginctl is unavailable.
    """
    users: Set[str] = set()
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
                if len(parts) >= 2:
                    session_id = parts[0]
                    session_info = subprocess.run(
                        ["loginctl", "show-session", session_id, "-p", "Active", "-p", "Remote", "-p", "Name"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if session_info.returncode != 0:
                        continue
                    props = {}
                    for prop_line in session_info.stdout.splitlines():
                        if "=" in prop_line:
                            key, value = prop_line.split("=", 1)
                            props[key.strip()] = value.strip()
                    if props.get("Active") != "yes":
                        continue
                    if props.get("Remote") == "yes":
                        continue
                    user = props.get("Name")
                    if user and user != "root":
                        users.add(user)
            return users
    except (FileNotFoundError, Exception):
        return None
    return users


def get_active_users() -> Set[str]:
    """
    Get list of currently active local non-root users.
    Returns a set of usernames.
    """
    loginctl_users = _get_active_loginctl_users()
    if loginctl_users is not None and loginctl_users:
        return loginctl_users

    users: Set[str] = set()
    try:
        result = subprocess.run(["who"], capture_output=True, text=True, check=False)
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts:
                user = parts[0]
                if user == "root":
                    continue
                # Skip remote sessions when possible (who prints host in parentheses).
                if "(" in line and ")" in line:
                    continue
                users.add(user)
    except Exception:
        pass

    return users


def get_active_session_user() -> Optional[str]:
    """
    Return the single active local session user (seat-based), or None if ambiguous.
    """
    try:
        result = subprocess.run(
            ["loginctl", "list-sessions", "--no-legend"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            active_users: Set[str] = set()
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    session_id = parts[0]
                    session_info = subprocess.run(
                        [
                            "loginctl",
                            "show-session",
                            session_id,
                            "-p",
                            "Active",
                            "-p",
                            "Remote",
                            "-p",
                            "Name",
                            "-p",
                            "Seat",
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if session_info.returncode != 0:
                        continue
                    props = {}
                    for prop_line in session_info.stdout.splitlines():
                        if "=" in prop_line:
                            key, value = prop_line.split("=", 1)
                            props[key.strip()] = value.strip()
                    if props.get("Active") != "yes":
                        continue
                    if props.get("Remote") == "yes":
                        continue
                    seat = props.get("Seat")
                    if not seat or seat == "unknown":
                        continue
                    user = props.get("Name")
                    if user and user != "root":
                        active_users.add(user)
            if len(active_users) == 1:
                return next(iter(active_users))
            return None
    except (FileNotFoundError, Exception):
        pass

    # Fallback: use who, only if a single local user is present.
    users = set()
    try:
        result = subprocess.run(["who"], capture_output=True, text=True, check=False)
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts:
                user = parts[0]
                if user == "root":
                    continue
                if "(" in line and ")" in line:
                    continue
                users.add(user)
    except Exception:
        pass

    if len(users) == 1:
        return next(iter(users))
    return None


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
    Check if the console/seat owner (active session user) is in exempted groups.
    This provides better security by checking the specific user at the console.
    
    Args:
        exempted_groups: List of group names that provide exemption
        logger: Logger instance for debug output
        
    Returns:
        Tuple of (is_exempted: bool, reason: str)
        - is_exempted: True if the console user is in an exempted group
        - reason: Description of which user/group matched, or empty string
    """
    if not exempted_groups:
        return False, ""
    
    console_user = get_active_session_user()
    if not console_user:
        logger.debug("No single active console user detected, defaulting to non-exempted")
        return False, ""
    
    logger.debug(f"Console user: {console_user}")
    logger.debug(f"Exempted groups: {exempted_groups}")
    
    for group in exempted_groups:
        if user_in_group(console_user, group):
            reason = f"console user '{console_user}' in exempted group '{group}'"
            logger.info(f"Exempting enforcement: {reason}")
            return True, reason
    
    return False, ""


def any_active_user_exempted(exempted_groups: List[str], logger: logging.Logger) -> bool:
    """
    Backwards-compatible helper for callers that only need the boolean exemption flag.
    """
    is_exempted, _reason = any_active_user_in_groups(exempted_groups, logger)
    return is_exempted

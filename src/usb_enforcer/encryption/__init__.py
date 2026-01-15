"""
USB Encryption Enforcement Module

Handles enforcement of encryption policies for USB devices:
- Device classification (plain/encrypted)
- LUKS encryption/decryption operations
- Read-only enforcement for plaintext devices
- Udev monitoring and event handling
- User and group exemption handling
"""

from .classify import classify_device
from .crypto_engine import encrypt_device, unlock_luks
from .enforcer import enforce_policy
from .udev_monitor import start_monitor
from .user_utils import any_active_user_in_groups

__all__ = [
    'classify_device',
    'encrypt_device',
    'unlock_luks',
    'enforce_policy',
    'start_monitor',
    'any_active_user_in_groups',
]

__version__ = '1.0.0'

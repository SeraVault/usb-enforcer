from __future__ import annotations

# Device classifications
PLAINTEXT = "plaintext"
LUKS1 = "luks1"
LUKS2_LOCKED = "luks2_locked"
LUKS2_UNLOCKED = "luks2_unlocked"
MAPPER = "mapper"
UNKNOWN = "unknown"

# Journald keys
LOG_KEY_EVENT = "USB_EE_EVENT"
LOG_KEY_DEVNODE = "DEVNODE"
LOG_KEY_ACTION = "ACTION"
LOG_KEY_CLASSIFICATION = "CLASSIFICATION"
LOG_KEY_RESULT = "RESULT"
LOG_KEY_POLICY_SOURCE = "POLICY_SOURCE"
LOG_KEY_SERIAL = "SERIAL"
LOG_KEY_DEVTYPE = "DEVTYPE"
LOG_KEY_BUS = "BUS"

# Events
EVENT_INSERT = "insert"
EVENT_CLASSIFY = "classify"
EVENT_ENFORCE = "enforce"
EVENT_UNLOCK = "unlock"
EVENT_ENCRYPT = "encrypt"
EVENT_ERROR = "error"

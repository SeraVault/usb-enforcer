from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


DEFAULT_CONFIG_PATH = Path("/etc/usb-encryption-enforcer/config.toml")


@dataclass
class Config:
    enforce_on_usb_only: bool = True
    allow_luks1_readonly: bool = True
    default_plain_mount_opts: List[str] = field(default_factory=lambda: ["nodev", "nosuid", "noexec", "ro"])
    default_encrypted_mount_opts: List[str] = field(default_factory=lambda: ["nodev", "nosuid", "rw"])
    require_noexec_on_plain: bool = True
    min_passphrase_length: int = 12
    encryption_target_mode: str = "whole_disk"
    filesystem_type: str = "exfat"
    notification_enabled: bool = True
    kdf: dict = field(default_factory=lambda: {"type": "argon2id"})
    cipher: dict = field(default_factory=lambda: {"type": "aes-xts-plain64", "key_size": 512})

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
        if not cfg_path.exists():
            return cls()
        with cfg_path.open("rb") as f:
            parsed = tomllib.load(f)
        return cls(
            enforce_on_usb_only=parsed.get("enforce_on_usb_only", True),
            allow_luks1_readonly=parsed.get("allow_luks1_readonly", True),
            default_plain_mount_opts=parsed.get("default_plain_mount_opts", ["nodev", "nosuid", "noexec", "ro"]),
            default_encrypted_mount_opts=parsed.get("default_encrypted_mount_opts", ["nodev", "nosuid", "rw"]),
            require_noexec_on_plain=parsed.get("require_noexec_on_plain", True),
            min_passphrase_length=parsed.get("min_passphrase_length", 12),
            encryption_target_mode=parsed.get("encryption_target_mode", "whole_disk"),
            filesystem_type=parsed.get("filesystem_type", "exfat"),
            notification_enabled=parsed.get("notification_enabled", True),
            kdf=parsed.get("kdf", {"type": "argon2id"}),
            cipher=parsed.get("cipher", {"type": "aes-xts-plain64", "key_size": 512}),
        )

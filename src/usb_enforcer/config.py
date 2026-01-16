from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Any

DEFAULT_CONFIG_PATH = Path("/etc/usb-enforcer/config.toml")

# Import content verification config if available
try:
    from .content_verification.config import ContentScanningConfig
    CONTENT_VERIFICATION_AVAILABLE = True
except ImportError:
    CONTENT_VERIFICATION_AVAILABLE = False
    ContentScanningConfig = None


@dataclass
class Config:
    enforce_on_usb_only: bool = True
    allow_luks1_readonly: bool = True
    allow_plaintext_write_with_scanning: bool = False  # Allow write to plaintext drives if content scanning is enabled
    default_plain_mount_opts: List[str] = field(default_factory=lambda: ["nodev", "nosuid", "noexec", "ro"])
    default_encrypted_mount_opts: List[str] = field(default_factory=lambda: ["nodev", "nosuid", "rw"])
    require_noexec_on_plain: bool = True
    min_passphrase_length: int = 12
    encryption_target_mode: str = "whole_disk"
    filesystem_type: str = "exfat"
    notification_enabled: bool = True
    exempted_groups: List[str] = field(default_factory=list)
    secret_token_ttl_seconds: int = 300
    secret_token_max: int = 128
    kdf: dict = field(default_factory=lambda: {"type": "argon2id"})
    cipher: dict = field(default_factory=lambda: {"type": "aes-xts-plain64", "key_size": 512})
    content_scanning: Optional[Any] = None  # ContentScanningConfig when available

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
        if not cfg_path.exists():
            return cls()
        with cfg_path.open("rb") as f:
            parsed = tomllib.load(f)
        
        # Parse content scanning config if available
        content_scanning = None
        if CONTENT_VERIFICATION_AVAILABLE and "content_scanning" in parsed:
            try:
                content_scanning = ContentScanningConfig.from_dict(
                    parsed["content_scanning"]
                )
            except Exception:
                # If parsing fails, content scanning will be disabled
                pass
        
        return cls(
            enforce_on_usb_only=parsed.get("enforce_on_usb_only", True),
            allow_luks1_readonly=parsed.get("allow_luks1_readonly", True),
            allow_plaintext_write_with_scanning=parsed.get("allow_plaintext_write_with_scanning", False),
            default_plain_mount_opts=parsed.get("default_plain_mount_opts", ["nodev", "nosuid", "noexec", "ro"]),
            default_encrypted_mount_opts=parsed.get("default_encrypted_mount_opts", ["nodev", "nosuid", "rw"]),
            require_noexec_on_plain=parsed.get("require_noexec_on_plain", True),
            min_passphrase_length=parsed.get("min_passphrase_length", 12),
            encryption_target_mode=parsed.get("encryption_target_mode", "whole_disk"),
            filesystem_type=parsed.get("filesystem_type", "exfat"),
            notification_enabled=parsed.get("notification_enabled", True),
            exempted_groups=parsed.get("exempted_groups", []),
            secret_token_ttl_seconds=parsed.get("secret_token_ttl_seconds", 300),
            secret_token_max=parsed.get("secret_token_max", 128),
            kdf=parsed.get("kdf", {"type": "argon2id"}),
            cipher=parsed.get("cipher", {"type": "aes-xts-plain64", "key_size": 512}),
            content_scanning=content_scanning,
        )

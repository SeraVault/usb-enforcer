"""Unit tests for configuration loading and parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from usb_enforcer import config as config_module


class TestConfigLoading:
    """Test configuration loading."""
    
    def test_load_default_config(self):
        """Test loading with default values when file doesn't exist."""
        cfg = config_module.Config.load(Path("/nonexistent/config.toml"))
        
        assert cfg.enforce_on_usb_only is True
        assert cfg.allow_luks1_readonly is True
        assert cfg.min_passphrase_length == 12
        assert cfg.encryption_target_mode == "whole_disk"
        assert cfg.filesystem_type == "exfat"
        assert cfg.notification_enabled is True
        assert cfg.require_noexec_on_plain is True
        assert "nodev" in cfg.default_plain_mount_opts
        assert "nosuid" in cfg.default_plain_mount_opts
        assert "noexec" in cfg.default_plain_mount_opts
        assert "ro" in cfg.default_plain_mount_opts
        assert cfg.exempted_groups == []
    
    def test_load_from_file(self, mock_config_file):
        """Test loading configuration from file."""
        cfg = config_module.Config.load(mock_config_file)
        
        assert cfg.enforce_on_usb_only is True
        assert cfg.allow_luks1_readonly is True
        assert cfg.min_passphrase_length == 12
        assert cfg.encryption_target_mode == "whole_disk"
        assert cfg.filesystem_type == "exfat"
        assert cfg.exempted_groups == ["usb-exempt"]
        assert cfg.kdf["type"] == "argon2id"
        assert cfg.cipher["type"] == "aes-xts-plain64"
        assert cfg.cipher["key_size"] == 512
        assert cfg.content_scanning is None

    def test_load_content_scanning_flat_keys(self, temp_dir):
        """Test flat content_scanning keys map into nested config."""
        config_path = temp_dir / "config.toml"
        config_path.write_text('''
[content_scanning]
enabled = true
action = "warn"
enabled_categories = ["financial", "personal", "authentication"]
max_file_size_mb = 42
scan_timeout_seconds = 25
large_file_scan_mode = "full"
archive_scanning_enabled = false
document_scanning_enabled = true
ngram_analysis_enabled = false
cache_enabled = true
cache_max_size_mb = 5
cache_ttl_hours = 1
''')
        
        cfg = config_module.Config.load(config_path)
        cs = cfg.content_scanning
        
        assert cs is not None
        assert cs.enabled is True
        assert cs.policy.action == "warn"
        assert cs.patterns.enabled_categories == ["financial", "pii", "corporate"]
        assert cs.max_file_size_mb == 42
        assert cs.max_scan_time_seconds == 25
        assert cs.large_file_scan_mode == "full"
        assert cs.archives.scan_archives is False
        assert cs.documents.scan_documents is True
        assert cs.ngrams.enabled is False
        assert cs.enable_cache is True
        assert cs.cache_size_mb == 5
        assert cs.cache_ttl_hours == 1
    
    def test_load_empty_config(self, mock_empty_config):
        """Test loading empty configuration file uses defaults."""
        cfg = config_module.Config.load(mock_empty_config)
        
        assert cfg.enforce_on_usb_only is True
        assert cfg.min_passphrase_length == 12


class TestConfigValues:
    """Test configuration value validation."""
    
    def test_custom_passphrase_length(self, temp_dir):
        """Test custom minimum passphrase length."""
        config_path = temp_dir / "config.toml"
        config_path.write_text('min_passphrase_length = 16')
        
        cfg = config_module.Config.load(config_path)
        assert cfg.min_passphrase_length == 16
    
    def test_custom_filesystem_type(self, temp_dir):
        """Test custom filesystem type."""
        config_path = temp_dir / "config.toml"
        config_path.write_text('filesystem_type = "ext4"')
        
        cfg = config_module.Config.load(config_path)
        assert cfg.filesystem_type == "ext4"
    
    def test_custom_mount_options(self, temp_dir):
        """Test custom mount options."""
        config_path = temp_dir / "config.toml"
        config_path.write_text('''
default_plain_mount_opts = ["nodev", "ro"]
default_encrypted_mount_opts = ["nodev", "rw", "noatime"]
''')
        
        cfg = config_module.Config.load(config_path)
        assert cfg.default_plain_mount_opts == ["nodev", "ro"]
        assert cfg.default_encrypted_mount_opts == ["nodev", "rw", "noatime"]
    
    def test_exempted_groups(self, temp_dir):
        """Test exempted groups configuration."""
        config_path = temp_dir / "config.toml"
        config_path.write_text('exempted_groups = ["group1", "group2"]')
        
        cfg = config_module.Config.load(config_path)
        assert "group1" in cfg.exempted_groups
        assert "group2" in cfg.exempted_groups
    
    def test_kdf_configuration(self, temp_dir):
        """Test KDF configuration."""
        config_path = temp_dir / "config.toml"
        config_path.write_text('''
[kdf]
type = "pbkdf2"
iterations = 100000
''')
        
        cfg = config_module.Config.load(config_path)
        assert cfg.kdf["type"] == "pbkdf2"
        assert cfg.kdf["iterations"] == 100000
    
    def test_cipher_configuration(self, temp_dir):
        """Test cipher configuration."""
        config_path = temp_dir / "config.toml"
        config_path.write_text('''
[cipher]
type = "aes-cbc-plain"
key_size = 256
''')
        
        cfg = config_module.Config.load(config_path)
        assert cfg.cipher["type"] == "aes-cbc-plain"
        assert cfg.cipher["key_size"] == 256
    
    def test_encryption_target_modes(self, temp_dir):
        """Test different encryption target modes."""
        for mode in ["whole_disk", "partition"]:
            config_path = temp_dir / "config.toml"
            config_path.write_text(f'encryption_target_mode = "{mode}"')
            
            cfg = config_module.Config.load(config_path)
            assert cfg.encryption_target_mode == mode

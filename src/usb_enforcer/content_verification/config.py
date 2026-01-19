"""
Configuration for content scanning module.

Handles loading and validation of content scanning settings.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class PatternConfig:
    """Pattern detection configuration"""
    enabled_categories: List[str] = field(default_factory=lambda: ['pii', 'financial', 'corporate'])
    disabled_patterns: List[str] = field(default_factory=list)
    custom_patterns: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ArchiveConfig:
    """Archive scanning configuration"""
    scan_archives: bool = True
    max_depth: int = 5
    max_members: int = 1000
    max_extract_size_mb: int = 100
    scan_timeout_seconds: int = 30
    block_encrypted_archives: bool = True
    supported_formats: List[str] = field(default_factory=lambda: ['zip', 'tar', 'tar.gz', 'tar.bz2', 'tar.xz', '7z'])


@dataclass
class DocumentConfig:
    """Document scanning configuration"""
    scan_documents: bool = True
    supported_formats: List[str] = field(default_factory=lambda: ['pdf', 'docx', 'xlsx', 'pptx', 'odt', 'ods'])


@dataclass
class NgramConfig:
    """N-gram analysis configuration"""
    enabled: bool = True
    block_threshold: float = 0.65
    warn_threshold: float = 0.45
    character_ngram_size: int = 3
    word_ngram_size: int = 2


@dataclass
class EntropyConfig:
    """Entropy analysis configuration"""
    enabled: bool = True
    threshold: float = 7.5
    block_size_kb: int = 1


@dataclass
class PolicyConfig:
    """Policy enforcement configuration"""
    action: str = 'block'  # block, warn, log
    notify_user: bool = True
    notification_message: str = "File blocked: contains sensitive data"
    allow_override: bool = False
    exempt_users: List[str] = field(default_factory=list)
    exempt_groups: List[str] = field(default_factory=list)
    exempt_extensions: List[str] = field(default_factory=lambda: ['.iso', '.img', '.vmdk'])


@dataclass
class LoggingConfig:
    """Logging configuration"""
    log_all_scans: bool = False
    log_blocked_only: bool = True
    log_to_journald: bool = True
    log_to_file: Optional[str] = "/var/log/usb-enforcer/content-scans.log"
    max_log_age_days: int = 90
    syslog_enabled: bool = False
    syslog_server: Optional[str] = None


@dataclass
class ContentScanningConfig:
    """
    Master configuration for content scanning.
    
    This class aggregates all content scanning configuration options
    and provides methods to load from TOML configuration.
    """
    enabled: bool = True
    scan_encrypted_devices: bool = True  # Deprecated: use enforce_on_encrypted_devices
    enforce_on_encrypted_devices: bool = True  # If False, only enforce on unencrypted USB
    
    # Performance settings
    max_file_size_mb: int = 500
    oversize_action: str = "block"  # block, allow_unscanned
    max_scan_time_seconds: int = 30
    max_concurrent_scans: int = 4
    
    # Caching
    enable_cache: bool = True
    cache_size_mb: int = 100
    cache_ttl_hours: int = 24
    
    # Error handling
    block_on_error: bool = True
    
    # Sub-configurations
    patterns: PatternConfig = field(default_factory=PatternConfig)
    archives: ArchiveConfig = field(default_factory=ArchiveConfig)
    documents: DocumentConfig = field(default_factory=DocumentConfig)
    ngrams: NgramConfig = field(default_factory=NgramConfig)
    entropy: EntropyConfig = field(default_factory=EntropyConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'ContentScanningConfig':
        """
        Create configuration from dictionary.
        
        Args:
            config_dict: Dictionary from parsed TOML
            
        Returns:
            ContentScanningConfig instance
        """
        # Extract sub-configurations (support nested or flat keys)
        def _copy_section(name: str) -> Dict[str, Any]:
            section = config_dict.get(name, {})
            return dict(section) if isinstance(section, dict) else {}

        patterns_dict = _copy_section('patterns')
        archives_dict = _copy_section('archives')
        documents_dict = _copy_section('documents')
        ngrams_dict = _copy_section('ngrams')
        entropy_dict = _copy_section('entropy')
        policy_dict = _copy_section('policy')
        logging_dict = _copy_section('logging')

        if 'enabled_categories' in config_dict:
            patterns_dict.setdefault('enabled_categories', config_dict.get('enabled_categories'))
        if 'disabled_patterns' in config_dict:
            patterns_dict.setdefault('disabled_patterns', config_dict.get('disabled_patterns'))
        if 'custom_patterns' in config_dict:
            patterns_dict.setdefault('custom_patterns', config_dict.get('custom_patterns'))
        if 'custom' in config_dict:
            patterns_dict.setdefault('custom', config_dict.get('custom'))

        if 'action' in config_dict:
            policy_dict.setdefault('action', config_dict.get('action'))

        if 'archive_scanning_enabled' in config_dict:
            archives_dict.setdefault('scan_archives', config_dict.get('archive_scanning_enabled'))
        if 'max_archive_depth' in config_dict:
            archives_dict.setdefault('max_depth', config_dict.get('max_archive_depth'))
        if 'max_archive_members' in config_dict:
            archives_dict.setdefault('max_members', config_dict.get('max_archive_members'))
        if 'max_extract_size_mb' in config_dict:
            archives_dict.setdefault('max_extract_size_mb', config_dict.get('max_extract_size_mb'))
        if 'scan_timeout_seconds' in config_dict:
            archives_dict.setdefault('scan_timeout_seconds', config_dict.get('scan_timeout_seconds'))

        if 'document_scanning_enabled' in config_dict:
            documents_dict.setdefault('scan_documents', config_dict.get('document_scanning_enabled'))

        if 'ngram_analysis_enabled' in config_dict:
            ngrams_dict.setdefault('enabled', config_dict.get('ngram_analysis_enabled'))

        if 'cache_enabled' in config_dict:
            config_dict = dict(config_dict)
            config_dict.setdefault('enable_cache', config_dict.get('cache_enabled'))
        if 'cache_max_size_mb' in config_dict:
            config_dict = dict(config_dict)
            config_dict.setdefault('cache_size_mb', config_dict.get('cache_max_size_mb'))

        if 'scan_timeout_seconds' in config_dict:
            config_dict = dict(config_dict)
            config_dict.setdefault('max_scan_time_seconds', config_dict.get('scan_timeout_seconds'))

        def _normalize_categories(categories: List[str]) -> List[str]:
            if not categories:
                return categories
            normalized = []
            for category in categories:
                if category == 'personal':
                    normalized.append('pii')
                elif category == 'authentication':
                    normalized.append('corporate')
                else:
                    normalized.append(category)
            return normalized
        
        return cls(
            enabled=config_dict.get('enabled', True),
            scan_encrypted_devices=config_dict.get('scan_encrypted_devices', True),
            enforce_on_encrypted_devices=config_dict.get('enforce_on_encrypted_devices', True),
            max_file_size_mb=config_dict.get('max_file_size_mb', 500),
            oversize_action=config_dict.get('oversize_action', 'block'),
            max_scan_time_seconds=config_dict.get('max_scan_time_seconds', 30),
            max_concurrent_scans=config_dict.get('max_concurrent_scans', 4),
            enable_cache=config_dict.get('enable_cache', True),
            cache_size_mb=config_dict.get('cache_size_mb', 100),
            cache_ttl_hours=config_dict.get('cache_ttl_hours', 24),
            block_on_error=config_dict.get('block_on_error', True),
            patterns=PatternConfig(
                enabled_categories=_normalize_categories(
                    patterns_dict.get('enabled_categories', ['pii', 'financial', 'corporate'])
                ),
                disabled_patterns=patterns_dict.get('disabled_patterns', []),
                custom_patterns=patterns_dict.get('custom', patterns_dict.get('custom_patterns', []))
            ),
            archives=ArchiveConfig(
                scan_archives=archives_dict.get('scan_archives', True),
                max_depth=archives_dict.get('max_depth', 5),
                max_members=archives_dict.get('max_members', 1000),
                max_extract_size_mb=archives_dict.get('max_extract_size_mb', 100),
                scan_timeout_seconds=archives_dict.get('scan_timeout_seconds', 30),
                block_encrypted_archives=archives_dict.get('block_encrypted_archives', True),
                supported_formats=archives_dict.get('supported_formats', 
                                                   ['zip', 'tar', 'tar.gz', 'tar.bz2', 'tar.xz', '7z'])
            ),
            documents=DocumentConfig(
                scan_documents=documents_dict.get('scan_documents', True),
                supported_formats=documents_dict.get('supported_formats',
                                                    ['pdf', 'docx', 'xlsx', 'pptx', 'odt', 'ods'])
            ),
            ngrams=NgramConfig(
                enabled=ngrams_dict.get('enabled', True),
                block_threshold=ngrams_dict.get('block_threshold', 0.65),
                warn_threshold=ngrams_dict.get('warn_threshold', 0.45),
                character_ngram_size=ngrams_dict.get('character_ngram_size', 3),
                word_ngram_size=ngrams_dict.get('word_ngram_size', 2)
            ),
            entropy=EntropyConfig(
                enabled=entropy_dict.get('enabled', True),
                threshold=entropy_dict.get('threshold', 7.5),
                block_size_kb=entropy_dict.get('block_size_kb', 1)
            ),
            policy=PolicyConfig(
                action=policy_dict.get('action', 'block'),
                notify_user=policy_dict.get('notify_user', True),
                notification_message=policy_dict.get('notification_message', 
                                                     "File blocked: contains sensitive data"),
                allow_override=policy_dict.get('allow_override', False),
                exempt_users=policy_dict.get('exempt_users', []),
                exempt_groups=policy_dict.get('exempt_groups', []),
                exempt_extensions=policy_dict.get('exempt_extensions', ['.iso', '.img', '.vmdk'])
            ),
            logging=LoggingConfig(
                log_all_scans=logging_dict.get('log_all_scans', False),
                log_blocked_only=logging_dict.get('log_blocked_only', True),
                log_to_journald=logging_dict.get('log_to_journald', True),
                log_to_file=logging_dict.get('log_to_file', '/var/log/usb-enforcer/content-scans.log'),
                max_log_age_days=logging_dict.get('max_log_age_days', 90),
                syslog_enabled=logging_dict.get('syslog_enabled', False),
                syslog_server=logging_dict.get('syslog_server', None)
            )
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            'enabled': self.enabled,
            'scan_encrypted_devices': self.scan_encrypted_devices,
            'enforce_on_encrypted_devices': self.enforce_on_encrypted_devices,
            'max_file_size_mb': self.max_file_size_mb,
            'oversize_action': self.oversize_action,
            'max_scan_time_seconds': self.max_scan_time_seconds,
            'max_memory_per_scan_mb': self.max_memory_per_scan_mb,
            'max_concurrent_scans': self.max_concurrent_scans,
            'enable_cache': self.enable_cache,
            'cache_size_mb': self.cache_size_mb,
            'cache_ttl_hours': self.cache_ttl_hours,
            'block_on_error': self.block_on_error,
        }
    
    def get_scanner_config(self) -> Dict[str, Any]:
        """Get configuration dict for ContentScanner"""
        return {
            'enabled_categories': self.patterns.enabled_categories,
            'disabled_patterns': self.patterns.disabled_patterns,
            'custom_patterns': self.patterns.custom_patterns,
            'enable_cache': self.enable_cache,
            'cache_size_mb': self.cache_size_mb,
            'cache_ttl_hours': self.cache_ttl_hours,
            'max_file_size_mb': self.max_file_size_mb,
            'max_scan_time_seconds': self.max_scan_time_seconds,
            'block_threshold': self.ngrams.block_threshold,
            'warn_threshold': self.ngrams.warn_threshold,
            'ngram_enabled': self.ngrams.enabled,
            'ngram_character_size': self.ngrams.character_ngram_size,
            'ngram_word_size': self.ngrams.word_ngram_size,
            'action': self.policy.action,
            'block_on_error': self.block_on_error,
        }

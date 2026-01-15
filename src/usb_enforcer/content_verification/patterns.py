"""
Pattern library for detecting sensitive data.

Provides validators and regex patterns for various types of sensitive information
including PII, financial data, and corporate credentials.
"""

import re
import hashlib
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum


class PatternCategory(Enum):
    """Categories of sensitive data patterns"""
    PII = "pii"
    FINANCIAL = "financial"
    MEDICAL = "medical"
    CORPORATE = "corporate"
    CUSTOM = "custom"


class PatternSeverity(Enum):
    """Severity levels for pattern matches"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Pattern:
    """Represents a detection pattern"""
    name: str
    regex: str
    category: PatternCategory
    severity: PatternSeverity
    description: str
    validator: Optional[callable] = None
    
    def __post_init__(self):
        """Compile regex pattern"""
        self.compiled_regex = re.compile(self.regex, re.IGNORECASE)


@dataclass
class PatternMatch:
    """Represents a pattern match in content"""
    pattern_name: str
    pattern_category: str
    severity: str
    matched_text: str  # Should NEVER be logged
    position: int
    context: str = ""  # 50 chars before/after (safe to log)
    
    def get_safe_match_indicator(self) -> str:
        """Get a safe representation for logging (no actual value)"""
        return f"{self.pattern_name} at position {self.position}"


class SSNValidator:
    """Validates Social Security Numbers"""
    
    PATTERN = r'\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b'
    
    @staticmethod
    def validate(match: str) -> bool:
        """
        Validate SSN format and check for known invalid patterns.
        
        Invalid SSNs:
        - Area number 000, 666, or 900-999
        - Group number 00
        - Serial number 0000
        """
        # Remove non-digits
        digits = re.sub(r'\D', '', match)
        
        if len(digits) != 9:
            return False
        
        area = int(digits[:3])
        group = int(digits[3:5])
        serial = int(digits[5:9])
        
        # Check invalid patterns
        if area == 0 or area == 666 or area >= 900:
            return False
        if group == 0:
            return False
        if serial == 0:
            return False
        
        # Check common test SSNs
        test_ssns = {
            '078051120',  # Woolworth wallet SSN
            '219099999',  # Advertisement SSN
        }
        if digits in test_ssns:
            return False
        
        return True


class CreditCardValidator:
    """Validates credit card numbers using Luhn algorithm"""
    
    PATTERN = r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'
    
    @staticmethod
    def luhn_check(card_number: str) -> bool:
        """Validate credit card using Luhn algorithm"""
        # Remove non-digits
        digits = re.sub(r'\D', '', card_number)
        
        if len(digits) < 13 or len(digits) > 19:
            return False
        
        # Luhn algorithm
        total = 0
        reverse_digits = digits[::-1]
        
        for i, digit in enumerate(reverse_digits):
            n = int(digit)
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        
        return total % 10 == 0
    
    @staticmethod
    def validate(match: str) -> bool:
        """Validate credit card number"""
        return CreditCardValidator.luhn_check(match)


class EmailValidator:
    """Validates email addresses"""
    
    PATTERN = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    
    @staticmethod
    def validate(match: str) -> bool:
        """Basic email validation"""
        # Already matched by regex, just check length
        return len(match) <= 254  # RFC 5321


class SwiftCodeValidator:
    """Validates SWIFT/BIC codes"""
    
    PATTERN = r'\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?\b'
    
    # Common ISO 3166-1 alpha-2 country codes
    VALID_COUNTRY_CODES = {
        'US', 'GB', 'DE', 'FR', 'IT', 'ES', 'NL', 'BE', 'CH', 'AT',
        'SE', 'NO', 'DK', 'FI', 'IE', 'PT', 'GR', 'PL', 'CZ', 'HU',
        'RO', 'BG', 'HR', 'SI', 'SK', 'LT', 'LV', 'EE', 'LU', 'MT',
        'CY', 'CA', 'MX', 'BR', 'AR', 'CL', 'CO', 'PE', 'VE', 'AU',
        'NZ', 'JP', 'CN', 'KR', 'IN', 'SG', 'HK', 'TH', 'MY', 'ID',
        'PH', 'VN', 'AE', 'SA', 'IL', 'TR', 'ZA', 'EG', 'NG', 'KE',
        'RU', 'UA', 'BY', 'KZ', 'IS', 'LI', 'MC', 'SM', 'VA', 'AD'
    }
    
    @staticmethod
    def validate(match: str) -> bool:
        """
        Validate SWIFT/BIC code format.
        
        Format: AAAABBCCXXX
        - AAAA: 4 letter institution code
        - BB: 2 letter country code (ISO 3166-1)
        - CC: 2 character location code
        - XXX: optional 3 character branch code
        """
        if len(match) not in (8, 11):
            return False
        
        # Extract country code (positions 4-5, 0-indexed)
        country_code = match[4:6].upper()
        
        # Check if it's a valid country code
        if country_code not in SwiftCodeValidator.VALID_COUNTRY_CODES:
            return False
        
        # Additional check: first 4 chars should be letters only
        if not match[:4].isalpha():
            return False
        
        return True


class APIKeyValidator:
    """Validates various API key formats"""
    
    PATTERNS = {
        'aws_access_key': r'AKIA[0-9A-Z]{16}',
        'aws_secret_key': r'[A-Za-z0-9/+=]{40}',
        'github_token': r'ghp_[A-Za-z0-9]{36}',
        'github_oauth': r'gho_[A-Za-z0-9]{36}',
        'slack_token': r'xox[baprs]-[0-9]{10,12}-[0-9]{10,12}-[A-Za-z0-9]{24,32}',
        'google_api': r'AIza[0-9A-Za-z_-]{35}',
        'stripe_key': r'sk_live_[0-9a-zA-Z]{24,}',
        'jwt': r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
    }
    
    @staticmethod
    def validate(match: str, key_type: Optional[str] = None) -> bool:
        """Validate API key format"""
        # Basic validation - check length and character set
        if len(match) < 20:
            return False
        
        if key_type == 'jwt':
            # JWT has three parts separated by dots
            parts = match.split('.')
            return len(parts) == 3
        
        return True


class PrivateKeyValidator:
    """Detects private keys in various formats"""
    
    PATTERNS = {
        'rsa_private': r'-----BEGIN RSA PRIVATE KEY-----',
        'ec_private': r'-----BEGIN EC PRIVATE KEY-----',
        'openssh_private': r'-----BEGIN OPENSSH PRIVATE KEY-----',
        'pgp_private': r'-----BEGIN PGP PRIVATE KEY BLOCK-----',
    }
    
    @staticmethod
    def validate(match: str) -> bool:
        """Always return True - presence of header is enough"""
        return True


class PatternLibrary:
    """
    Central registry of all detection patterns.
    
    This class provides a comprehensive library of patterns for detecting
    sensitive data across multiple categories.
    """
    
    def __init__(self, enabled_categories: Optional[List[str]] = None,
                 disabled_patterns: Optional[List[str]] = None):
        """
        Initialize pattern library.
        
        Args:
            enabled_categories: List of category names to enable (None = all)
            disabled_patterns: List of specific patterns to disable
        """
        self.enabled_categories = enabled_categories or []
        self.disabled_patterns = disabled_patterns or []
        self.patterns: List[Pattern] = []
        self.custom_patterns: List[Pattern] = []
        
        self._build_pattern_library()
    
    def _build_pattern_library(self):
        """Build the complete pattern library"""
        
        # PII patterns
        pii_patterns = [
            Pattern(
                name='ssn',
                regex=SSNValidator.PATTERN,
                category=PatternCategory.PII,
                severity=PatternSeverity.CRITICAL,
                description='Social Security Number',
                validator=SSNValidator.validate
            ),
            Pattern(
                name='email',
                regex=EmailValidator.PATTERN,
                category=PatternCategory.PII,
                severity=PatternSeverity.LOW,
                description='Email address',
                validator=EmailValidator.validate
            ),
            Pattern(
                name='phone_us',
                regex=r'\b(\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',
                category=PatternCategory.PII,
                severity=PatternSeverity.LOW,
                description='US phone number'
            ),
            Pattern(
                name='drivers_license',
                regex=r'\b[A-Z]{1,2}\d{5,8}\b',
                category=PatternCategory.PII,
                severity=PatternSeverity.HIGH,
                description='Driver\'s license number'
            ),
            Pattern(
                name='passport',
                regex=r'\b[A-Z]{1,2}\d{6,9}\b',
                category=PatternCategory.PII,
                severity=PatternSeverity.CRITICAL,
                description='Passport number'
            ),
            Pattern(
                name='date_of_birth',
                regex=r'\b(0[1-9]|1[0-2])[/-](0[1-9]|[12][0-9]|3[01])[/-](19|20)\d{2}\b',
                category=PatternCategory.PII,
                severity=PatternSeverity.MEDIUM,
                description='Date of birth'
            ),
        ]
        
        # Financial patterns
        financial_patterns = [
            Pattern(
                name='credit_card',
                regex=CreditCardValidator.PATTERN,
                category=PatternCategory.FINANCIAL,
                severity=PatternSeverity.CRITICAL,
                description='Credit card number',
                validator=CreditCardValidator.validate
            ),
            Pattern(
                name='bank_account',
                regex=r'\b\d{8,17}\b',
                category=PatternCategory.FINANCIAL,
                severity=PatternSeverity.HIGH,
                description='Bank account number'
            ),
            Pattern(
                name='iban',
                regex=r'\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b',
                category=PatternCategory.FINANCIAL,
                severity=PatternSeverity.HIGH,
                description='International Bank Account Number'
            ),
            Pattern(
                name='swift_code',
                regex=SwiftCodeValidator.PATTERN,
                category=PatternCategory.FINANCIAL,
                severity=PatternSeverity.MEDIUM,
                description='SWIFT/BIC code (4 letter bank + 2 letter country + 2 location + optional 3 branch)',
                validator=SwiftCodeValidator.validate
            ),
        ]
        
        # Medical patterns
        medical_patterns = [
            Pattern(
                name='npi',
                regex=r'\b\d{10}\b',
                category=PatternCategory.MEDICAL,
                severity=PatternSeverity.HIGH,
                description='National Provider Identifier'
            ),
            Pattern(
                name='mrn',
                regex=r'\bMRN[-:\s]?\d{6,10}\b',
                category=PatternCategory.MEDICAL,
                severity=PatternSeverity.CRITICAL,
                description='Medical Record Number'
            ),
        ]
        
        # Corporate patterns
        corporate_patterns = []
        
        # Add AWS patterns
        for key_type, pattern in APIKeyValidator.PATTERNS.items():
            corporate_patterns.append(
                Pattern(
                    name=key_type,
                    regex=pattern,
                    category=PatternCategory.CORPORATE,
                    severity=PatternSeverity.CRITICAL,
                    description=f'{key_type.replace("_", " ").title()} credential',
                    validator=lambda m, kt=key_type: APIKeyValidator.validate(m, kt)
                )
            )
        
        # Add private key patterns
        for key_type, pattern in PrivateKeyValidator.PATTERNS.items():
            corporate_patterns.append(
                Pattern(
                    name=key_type,
                    regex=pattern,
                    category=PatternCategory.CORPORATE,
                    severity=PatternSeverity.CRITICAL,
                    description=f'{key_type.replace("_", " ").title()}',
                    validator=PrivateKeyValidator.validate
                )
            )
        
        # Additional corporate patterns
        corporate_patterns.extend([
            Pattern(
                name='database_connection',
                regex=r'(mysql|postgresql|mongodb|redis)://[^\s]+',
                category=PatternCategory.CORPORATE,
                severity=PatternSeverity.CRITICAL,
                description='Database connection string'
            ),
            Pattern(
                name='generic_api_key',
                regex=r'api[_-]?key["\']?\s*[:=]\s*["\']?[A-Za-z0-9_-]{20,}',
                category=PatternCategory.CORPORATE,
                severity=PatternSeverity.HIGH,
                description='Generic API key'
            ),
            Pattern(
                name='generic_password',
                regex=r'password["\']?\s*[:=]\s*["\']?[^\s]{8,}',
                category=PatternCategory.CORPORATE,
                severity=PatternSeverity.HIGH,
                description='Password in configuration'
            ),
        ])
        
        # Combine all patterns
        all_patterns = pii_patterns + financial_patterns + medical_patterns + corporate_patterns
        
        # Filter based on enabled categories
        if self.enabled_categories:
            all_patterns = [
                p for p in all_patterns
                if p.category.value in self.enabled_categories
            ]
        
        # Filter out disabled patterns
        if self.disabled_patterns:
            all_patterns = [
                p for p in all_patterns
                if p.name not in self.disabled_patterns
            ]
        
        self.patterns = all_patterns
    
    def add_custom_pattern(self, name: str, regex: str, description: str,
                          severity: str = "high") -> None:
        """
        Add a custom pattern to the library.
        
        Args:
            name: Pattern identifier
            regex: Regular expression pattern
            description: Human-readable description
            severity: Severity level (low, medium, high, critical)
        """
        pattern = Pattern(
            name=name,
            regex=regex,
            category=PatternCategory.CUSTOM,
            severity=PatternSeverity[severity.upper()],
            description=description
        )
        self.custom_patterns.append(pattern)
    
    def get_all_patterns(self) -> List[Pattern]:
        """Get all enabled patterns including custom ones"""
        return self.patterns + self.custom_patterns
    
    def get_patterns_by_category(self, category: str) -> List[Pattern]:
        """Get all patterns in a specific category"""
        return [
            p for p in self.get_all_patterns()
            if p.category.value == category
        ]
    
    def scan_text(self, text: str) -> List[PatternMatch]:
        """
        Scan text for all patterns.
        
        Args:
            text: Text content to scan
            
        Returns:
            List of pattern matches found
        """
        matches = []
        
        for pattern in self.get_all_patterns():
            for match in pattern.compiled_regex.finditer(text):
                matched_text = match.group(0)
                
                # Apply validator if present
                if pattern.validator:
                    if not pattern.validator(matched_text):
                        continue  # Skip invalid matches
                
                # Get context (50 chars before and after)
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end]
                
                # Redact the actual match from context
                context = context.replace(matched_text, f"[{pattern.name.upper()}]")
                
                matches.append(
                    PatternMatch(
                        pattern_name=pattern.name,
                        pattern_category=pattern.category.value,
                        severity=pattern.severity.value,
                        matched_text=matched_text,
                        position=match.start(),
                        context=context
                    )
                )
        
        return matches
    
    def has_sensitive_data(self, text: str) -> bool:
        """
        Quick check if text contains any sensitive data.
        
        Args:
            text: Text content to check
            
        Returns:
            True if sensitive data found
        """
        return len(self.scan_text(text)) > 0

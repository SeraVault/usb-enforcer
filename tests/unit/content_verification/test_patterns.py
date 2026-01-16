"""Unit tests for pattern matching"""

import pytest
from usb_enforcer.content_verification.patterns import (
    PatternLibrary,
    SSNValidator,
    CreditCardValidator,
    PatternCategory,
)


class TestSSNValidator:
    """Test SSN pattern detection and validation"""
    
    def test_standard_format(self):
        """Test SSN with dashes"""
        assert SSNValidator.validate('123-45-6789')
    
    def test_no_dashes(self):
        """Test SSN without dashes"""
        assert SSNValidator.validate('123456789')
    
    def test_spaces(self):
        """Test SSN with spaces"""
        assert SSNValidator.validate('123 45 6789')
    
    def test_invalid_area_000(self):
        """Test invalid area number 000"""
        assert not SSNValidator.validate('000-45-6789')
    
    def test_invalid_area_666(self):
        """Test invalid area number 666"""
        assert not SSNValidator.validate('666-45-6789')
    
    def test_invalid_area_900(self):
        """Test invalid area number 900+"""
        assert not SSNValidator.validate('900-45-6789')
    
    def test_invalid_group_00(self):
        """Test invalid group number 00"""
        assert not SSNValidator.validate('123-00-6789')
    
    def test_invalid_serial_0000(self):
        """Test invalid serial number 0000"""
        assert not SSNValidator.validate('123-45-0000')
    
    def test_woolworth_test_ssn(self):
        """Test known invalid test SSN"""
        assert not SSNValidator.validate('078-05-1120')


class TestCreditCardValidator:
    """Test credit card pattern detection and Luhn validation"""
    
    def test_valid_visa(self):
        """Test valid Visa card"""
        assert CreditCardValidator.validate('4111-1111-1111-1111')
    
    def test_valid_visa_no_dashes(self):
        """Test valid Visa without dashes"""
        assert CreditCardValidator.validate('4111111111111111')
    
    def test_valid_mastercard(self):
        """Test valid Mastercard"""
        assert CreditCardValidator.validate('5555-5555-5555-4444')
    
    def test_invalid_luhn(self):
        """Test invalid Luhn checksum"""
        assert not CreditCardValidator.validate('4111-1111-1111-1112')
    
    def test_too_short(self):
        """Test number too short"""
        assert not CreditCardValidator.validate('1234-5678-9012')
    
    def test_too_long(self):
        """Test number too long"""
        assert not CreditCardValidator.validate('1234-5678-9012-3456-7890')


class TestPatternLibrary:
    """Test pattern library functionality"""
    
    def test_initialization(self):
        """Test library initialization"""
        lib = PatternLibrary()
        patterns = lib.get_all_patterns()
        assert len(patterns) > 0
    
    def test_category_filtering(self):
        """Test filtering by category"""
        lib = PatternLibrary(enabled_categories=['pii'])
        patterns = lib.get_all_patterns()
        
        # All patterns should be PII category
        for pattern in patterns:
            assert pattern.category == PatternCategory.PII
    
    def test_pattern_disabling(self):
        """Test disabling specific patterns"""
        lib = PatternLibrary(disabled_patterns=['email'])
        patterns = lib.get_all_patterns()
        
        # Email pattern should not be present
        pattern_names = [p.name for p in patterns]
        assert 'email' not in pattern_names
    
    def test_custom_pattern(self):
        """Test adding custom pattern"""
        lib = PatternLibrary()
        lib.add_custom_pattern(
            name='test_pattern',
            regex=r'TEST-\d{4}',
            description='Test pattern',
            severity='high'
        )
        
        patterns = lib.get_all_patterns()
        pattern_names = [p.name for p in patterns]
        assert 'test_pattern' in pattern_names
    
    def test_scan_text_with_ssn(self):
        """Test scanning text containing SSN"""
        lib = PatternLibrary()
        text = "My SSN is 123-45-6789 and I need help."
        
        matches = lib.scan_text(text)
        assert len(matches) > 0
        assert matches[0].pattern_name == 'ssn'
    
    def test_scan_text_with_credit_card(self):
        """Test scanning text containing credit card"""
        lib = PatternLibrary()
        text = "My card number is 4111-1111-1111-1111"
        
        matches = lib.scan_text(text)
        assert len(matches) > 0
        assert matches[0].pattern_name == 'credit_card'
    
    def test_scan_text_with_multiple_patterns(self):
        """Test scanning text with multiple sensitive data"""
        lib = PatternLibrary()
        text = "SSN: 123-45-6789, Card: 4111-1111-1111-1111, Email: user@example.com"
        
        matches = lib.scan_text(text)
        assert len(matches) >= 3
        
        pattern_names = [m.pattern_name for m in matches]
        assert 'ssn' in pattern_names
        assert 'credit_card' in pattern_names
        assert 'email' in pattern_names
    
    def test_scan_clean_text(self):
        """Test scanning text with no sensitive data"""
        lib = PatternLibrary()
        text = "This is clean text with no sensitive information."
        
        matches = lib.scan_text(text)
        assert len(matches) == 0
    
    def test_has_sensitive_data(self):
        """Test quick sensitive data check"""
        lib = PatternLibrary()
        
        assert lib.has_sensitive_data("SSN: 123-45-6789")
        assert not lib.has_sensitive_data("Clean text")
    
    def test_api_key_detection(self):
        """Test detection of API keys"""
        lib = PatternLibrary()
        text = "AWS Key: AKIAIOSFODNN7EXAMPLE"
        
        matches = lib.scan_text(text)
        assert len(matches) > 0
        assert any('aws' in m.pattern_name for m in matches)
    
    def test_github_token_detection(self):
        """Test detection of GitHub tokens"""
        lib = PatternLibrary()
        text = "Token: ghp_1234567890123456789012345678901234AB"
        
        matches = lib.scan_text(text)
        assert len(matches) > 0
        assert any('github' in m.pattern_name for m in matches)
    
    def test_private_key_detection(self):
        """Test detection of private keys"""
        lib = PatternLibrary()
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA"
        
        matches = lib.scan_text(text)
        assert len(matches) > 0
        assert any('private' in m.pattern_name.lower() for m in matches)


class TestPatternMatch:
    """Test PatternMatch functionality"""
    
    def test_safe_match_indicator(self):
        """Test that safe indicator doesn't reveal actual value"""
        from usb_enforcer.content_verification.patterns import PatternMatch
        
        match = PatternMatch(
            pattern_name='ssn',
            pattern_category='pii',
            severity='critical',
            matched_text='123-45-6789',
            position=10
        )
        
        indicator = match.get_safe_match_indicator()
        
        # Should not contain actual SSN
        assert '123-45-6789' not in indicator
        # Should contain pattern name and position
        assert 'ssn' in indicator
        assert '10' in indicator


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

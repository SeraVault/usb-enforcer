"""Unit tests for content scanner"""

import pytest
import tempfile
from pathlib import Path
from usb_enforcer.content_verification.scanner import ContentScanner, ScanResult, ScanAction


class TestContentScanner:
    """Test content scanner functionality"""
    
    def test_initialization(self):
        """Test scanner initialization"""
        scanner = ContentScanner()
        assert scanner is not None
        assert scanner.pattern_library is not None
    
    def test_scan_content_with_ssn(self):
        """Test scanning content containing SSN"""
        scanner = ContentScanner()
        content = b"My Social Security Number is 123-45-6789"
        
        result = scanner.scan_content(content, "test.txt")
        
        assert result.blocked is True
        assert result.action == ScanAction.BLOCK
        assert len(result.matches) > 0
        assert result.matches[0].pattern_name == 'ssn'
    
    def test_scan_content_clean(self):
        """Test scanning clean content"""
        scanner = ContentScanner()
        content = b"This is clean text with no sensitive data"
        
        result = scanner.scan_content(content, "test.txt")
        
        assert result.blocked is False
        assert result.action == ScanAction.ALLOW
        assert len(result.matches) == 0
    
    def test_scan_content_with_credit_card(self):
        """Test scanning content with credit card"""
        scanner = ContentScanner()
        content = b"Card: 4111-1111-1111-1111"
        
        result = scanner.scan_content(content, "test.txt")
        
        assert result.blocked is True
        assert len(result.matches) > 0
        assert result.matches[0].pattern_name == 'credit_card'
    
    def test_scan_small_file(self):
        """Test scanning small file"""
        scanner = ContentScanner()
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("SSN: 123-45-6789")
            filepath = Path(f.name)
        
        try:
            result = scanner.scan_file(filepath)
            
            assert result.blocked is True
            assert result.file_size > 0
            assert result.file_type == '.txt'
            assert result.scan_duration >= 0
        finally:
            filepath.unlink()
    
    def test_scan_nonexistent_file(self):
        """Test scanning nonexistent file"""
        scanner = ContentScanner()
        filepath = Path("/tmp/nonexistent_file.txt")
        
        result = scanner.scan_file(filepath)
        
        assert result.blocked is False
        assert "does not exist" in result.reason
    
    def test_scan_file_with_cache(self):
        """Test that caching works"""
        config = {'enable_cache': True}
        scanner = ContentScanner(config)
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("Clean content")
            filepath = Path(f.name)
        
        try:
            # First scan
            result1 = scanner.scan_file(filepath)
            
            # Second scan (should use cache)
            result2 = scanner.scan_file(filepath)
            
            assert result1.blocked == result2.blocked
            assert scanner.cache.hits > 0
        finally:
            filepath.unlink()
    
    def test_scan_file_exceeds_size_limit(self):
        """Test scanning file that exceeds size limit"""
        config = {'max_file_size_mb': 0.001}  # Very small limit
        scanner = ContentScanner(config)
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            # Write more than limit
            f.write("x" * 2000)
            filepath = Path(f.name)
        
        try:
            result = scanner.scan_file(filepath)
            
            assert result.blocked is True
            assert "exceeds size limit" in result.reason
        finally:
            filepath.unlink()
    
    def test_scan_exempt_extension(self):
        """Test that exempt extensions are skipped"""
        scanner = ContentScanner()
        
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.iso') as f:
            f.write(b"Binary data")
            filepath = Path(f.name)
        
        try:
            result = scanner.scan_file(filepath)
            
            assert result.blocked is False
            assert "Exempt" in result.reason
        finally:
            filepath.unlink()
    
    def test_custom_pattern(self):
        """Test scanning with custom pattern"""
        config = {
            'custom_patterns': [
                {
                    'name': 'employee_id',
                    'regex': r'EMP-\d{6}',
                    'description': 'Employee ID',
                    'severity': 'high'
                }
            ]
        }
        scanner = ContentScanner(config)
        
        content = b"Employee: EMP-123456"
        result = scanner.scan_content(content, "test.txt")
        
        assert result.blocked is True
        assert any(m.pattern_name == 'employee_id' for m in result.matches)
    
    def test_action_mode_warn(self):
        """Test warn action mode"""
        config = {'action': 'warn'}
        scanner = ContentScanner(config)
        
        content = b"SSN: 123-45-6789"
        result = scanner.scan_content(content, "test.txt")
        
        # Should find pattern but action is WARN
        assert result.action == ScanAction.WARN
        assert len(result.matches) > 0
    
    def test_statistics(self):
        """Test getting scanner statistics"""
        scanner = ContentScanner()
        stats = scanner.get_statistics()
        
        assert 'patterns_loaded' in stats
        assert stats['patterns_loaded'] > 0
        assert 'patterns_by_category' in stats


class TestScanResult:
    """Test ScanResult functionality"""
    
    def test_to_log_dict(self):
        """Test converting result to log dictionary"""
        from usb_enforcer.content_verification.patterns import PatternMatch
        
        match = PatternMatch(
            pattern_name='ssn',
            pattern_category='pii',
            severity='critical',
            matched_text='123-45-6789',
            position=10
        )
        
        result = ScanResult(
            blocked=True,
            action=ScanAction.BLOCK,
            reason="Detected SSN",
            matches=[match],
            file_size=100
        )
        
        log_dict = result.to_log_dict()
        
        # Verify log dict doesn't contain actual matched value
        assert 'pattern_matches' in log_dict
        for pattern_match in log_dict['pattern_matches']:
            assert 'matched_text' not in pattern_match
    
    def test_get_summary(self):
        """Test getting result summary"""
        result = ScanResult(
            blocked=False,
            action=ScanAction.ALLOW,
            reason="Clean"
        )
        
        summary = result.get_summary()
        assert "allowed" in summary.lower()
        
        from usb_enforcer.content_verification.patterns import PatternMatch
        
        match = PatternMatch(
            pattern_name='ssn',
            pattern_category='pii',
            severity='critical',
            matched_text='123-45-6789',
            position=10
        )
        
        result = ScanResult(
            blocked=True,
            action=ScanAction.BLOCK,
            matches=[match]
        )
        
        summary = result.get_summary()
        assert "blocked" in summary.lower()
        assert "ssn" in summary.lower()


class TestScanCache:
    """Test scan cache functionality"""
    
    def test_cache_hit(self):
        """Test cache hit"""
        from usb_enforcer.content_verification.scanner import ScanCache
        
        cache = ScanCache(max_size_mb=10)
        
        result = ScanResult(
            blocked=False,
            action=ScanAction.ALLOW
        )
        
        file_hash = "abc123"
        cache.put(file_hash, result, 100)
        
        cached_result = cache.get(file_hash)
        assert cached_result is not None
        assert cached_result.blocked == result.blocked
        assert cache.hits == 1
    
    def test_cache_miss(self):
        """Test cache miss"""
        from usb_enforcer.content_verification.scanner import ScanCache
        
        cache = ScanCache(max_size_mb=10)
        
        result = cache.get("nonexistent")
        assert result is None
        assert cache.misses == 1
    
    def test_cache_eviction(self):
        """Test cache eviction when full"""
        from usb_enforcer.content_verification.scanner import ScanCache
        
        cache = ScanCache(max_size_mb=0.001)  # Very small cache
        
        result = ScanResult(
            blocked=False,
            action=ScanAction.ALLOW
        )
        
        # Add entries until eviction occurs
        for i in range(10):
            cache.put(f"hash{i}", result, 1000)
        
        # First entries should be evicted
        assert cache.get("hash0") is None
    
    def test_cache_stats(self):
        """Test getting cache statistics"""
        from usb_enforcer.content_verification.scanner import ScanCache
        
        cache = ScanCache(max_size_mb=10)
        
        result = ScanResult(
            blocked=False,
            action=ScanAction.ALLOW
        )
        
        cache.put("hash1", result, 100)
        cache.get("hash1")  # Hit
        cache.get("hash2")  # Miss
        
        stats = cache.get_stats()
        
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['entries'] == 1
        assert 'hit_rate' in stats


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

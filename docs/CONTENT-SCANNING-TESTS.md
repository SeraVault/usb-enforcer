# Content Scanning Integration Tests

This document describes the comprehensive integration test suite for USB Enforcer's content scanning functionality with both encrypted and unencrypted USB drives.

## Overview

The test suite (`tests/integration/test_content_scanning.py`) verifies that:

1. **Encrypted USB drives** are properly scanned after unlock
2. **Unencrypted USB drives** are scanned when used by exempted users
3. **Sensitive data** (SSNs, credit cards, API keys, etc.) is detected and blocked
4. **Clean data** is allowed through without issues
5. **Performance** is acceptable for large files and concurrent operations

## Test Structure

### Test Classes

#### 1. `TestEncryptedDriveContentScanning`
Tests content scanning on LUKS2-encrypted USB drives.

**Tests:**
- `test_encrypted_drive_allows_clean_content` - Verifies clean files can be written
- `test_encrypted_drive_blocks_sensitive_content` - Verifies SSNs, credit cards are blocked
- `test_encrypted_drive_scans_archives` - Verifies ZIP archives are scanned

#### 2. `TestUnencryptedDriveContentScanning`
Tests content scanning on unencrypted USB drives for exempted users.

**Tests:**
- `test_unencrypted_drive_exempted_user_allows_clean_content` - Clean writes allowed for exempted users
- `test_unencrypted_drive_exempted_user_blocks_sensitive_content` - Sensitive data blocked
- `test_unencrypted_drive_non_exempted_user_read_only` - Non-exempted users get read-only access

#### 3. `TestContentScannerPatterns`
Tests individual pattern detection accuracy.

**Tests:**
- `test_ssn_detection` - Social Security Number patterns
- `test_credit_card_detection` - Credit card number patterns (with Luhn check)
- `test_api_key_detection` - API keys, tokens, AWS secrets

#### 4. `TestContentScannerPerformance`
Tests performance and resource usage.

**Tests:**
- `test_large_file_scanning` - 10MB file scans in < 5 seconds
- `test_concurrent_scanning` - Multiple files scanned concurrently

#### 5. `TestFuseManagerIntegration`
Tests FUSE overlay manager functionality.

**Tests:**
- `test_fuse_manager_initialization` - Manager initialized correctly
- `test_scanner_statistics` - Statistics collection works
- `test_fuse_mount_called_on_setup` - FUSE mount triggered appropriately

## Requirements

### System Requirements

1. **Root/sudo access** - Required for:
   - Creating loopback devices
   - Running cryptsetup (LUKS operations)
   - Mounting filesystems

2. **System packages:**
   ```bash
   # Fedora/RHEL
   sudo dnf install python3-pytest util-linux cryptsetup e2fsprogs
   
   # Ubuntu/Debian
   sudo apt install python3-pytest util-linux cryptsetup-bin e2fsprogs
   ```

3. **Python dependencies:**
   ```bash
   pip3 install -r requirements-test.txt
   ```

### Content Verification Module

Tests require the content verification module to be available:
- `usb_enforcer.content_verification.scanner`
- `usb_enforcer.content_verification.fuse_overlay`
- Dependencies: pdfplumber, python-docx, openpyxl, py7zr, rarfile, fusepy

## Running Tests

### Quick Start (Recommended)

Use the provided test runner script:

```bash
sudo ./run-content-scanning-tests.sh
```

This script:
- Checks all dependencies
- Installs Python requirements
- Runs tests with proper configuration
- Shows colored output with details

### Manual Execution

Run all content scanning tests:
```bash
sudo python3 -m pytest tests/integration/test_content_scanning.py -v
```

Run specific test class:
```bash
sudo python3 -m pytest tests/integration/test_content_scanning.py::TestEncryptedDriveContentScanning -v
```

Run specific test:
```bash
sudo python3 -m pytest tests/integration/test_content_scanning.py::TestContentScannerPatterns::test_ssn_detection -v
```

Run with detailed output:
```bash
sudo python3 -m pytest tests/integration/test_content_scanning.py -v --tb=short --capture=no
```

### Skip Tests

Skip tests requiring root:
```bash
python3 -m pytest tests/integration/test_content_scanning.py -v -m "not integration"
```

Skip tests requiring content verification:
```bash
# Tests automatically skip if module unavailable
python3 -m pytest tests/integration/test_content_scanning.py -v
```

## Test Fixtures

### Virtual USB Devices

Tests use **loopback devices** to simulate USB drives without physical hardware:

1. **`mock_usb_device`** - Creates 100MB virtual disk
2. **`encrypted_usb_device`** - LUKS2-encrypted virtual USB
3. **`unencrypted_usb_device`** - Plain ext4 virtual USB

### Configuration

**`content_scanning_config`** - Creates test config with:
```toml
[content_scanning]
enabled = true
scan_archives = true
scan_documents = true
block_on_detection = true
max_file_size_mb = 100

exempted_groups = ["usb-exempt"]
```

## How Tests Work

### Encrypted Drive Test Flow

1. Create 100MB loopback device
2. Format with `cryptsetup luksFormat --type luks2`
3. Unlock with `cryptsetup open`
4. Format unlocked mapper as ext4
5. Mount filesystem
6. Write test files (clean and sensitive)
7. Verify content scanning behavior
8. Cleanup: unmount, close LUKS, detach loop

### Unencrypted Drive Test Flow

1. Create 100MB loopback device
2. Format as ext4
3. Mock user exemption check
4. Simulate device insertion via daemon
5. Verify:
   - Exempted users get writable mount with scanning
   - Non-exempted users get read-only mount
   - Sensitive content is blocked
6. Cleanup: detach loop device

### Pattern Detection Tests

1. Create in-memory or temporary file with test data
2. Call `scanner.scan_content()` or `scanner.scan_file()`
3. Verify matches returned for sensitive patterns
4. Verify no false positives for clean data

## Expected Results

### Successful Test Run

```
============================= test session starts ==============================
tests/integration/test_content_scanning.py::TestEncryptedDriveContentScanning::test_encrypted_drive_allows_clean_content PASSED
tests/integration/test_content_scanning.py::TestEncryptedDriveContentScanning::test_encrypted_drive_blocks_sensitive_content PASSED
tests/integration/test_content_scanning.py::TestEncryptedDriveContentScanning::test_encrypted_drive_scans_archives PASSED
tests/integration/test_content_scanning.py::TestUnencryptedDriveContentScanning::test_unencrypted_drive_exempted_user_allows_clean_content PASSED
tests/integration/test_content_scanning.py::TestUnencryptedDriveContentScanning::test_unencrypted_drive_exempted_user_blocks_sensitive_content PASSED
tests/integration/test_content_scanning.py::TestUnencryptedDriveContentScanning::test_unencrypted_drive_non_exempted_user_read_only PASSED
tests/integration/test_content_scanning.py::TestContentScannerPatterns::test_ssn_detection PASSED
tests/integration/test_content_scanning.py::TestContentScannerPatterns::test_credit_card_detection PASSED
tests/integration/test_content_scanning.py::TestContentScannerPatterns::test_api_key_detection PASSED
tests/integration/test_content_scanning.py::TestContentScannerPerformance::test_large_file_scanning PASSED
tests/integration/test_content_scanning.py::TestContentScannerPerformance::test_concurrent_scanning PASSED
tests/integration/test_content_scanning.py::TestFuseManagerIntegration::test_fuse_manager_initialization PASSED
tests/integration/test_content_scanning.py::TestFuseManagerIntegration::test_scanner_statistics PASSED

========================== 13 tests passed in 15.23s ===========================
```

### Performance Benchmarks

- **Large file scanning**: < 5 seconds for 10MB file
- **Concurrent scanning**: 5 files simultaneously without errors
- **Pattern detection**: < 100ms for typical documents

## Troubleshooting

### "Permission denied" errors
```bash
# Ensure running with sudo
sudo ./run-content-scanning-tests.sh
```

### "losetup: cannot find unused device"
```bash
# Check available loop devices
sudo losetup -f

# Cleanup existing loops
sudo losetup -D
```

### "cryptsetup command not found"
```bash
# Install cryptsetup
sudo dnf install cryptsetup          # Fedora/RHEL
sudo apt install cryptsetup-bin      # Ubuntu/Debian
```

### "FUSE not available" errors
```bash
# Install FUSE and fusepy
sudo dnf install fuse fuse-libs
pip3 install fusepy

# Load FUSE kernel module
sudo modprobe fuse
```

### Tests skip with "Content verification not available"
```bash
# Install content scanning dependencies
pip3 install -r requirements.txt

# Verify imports work
python3 -c "from usb_enforcer.content_verification.scanner import ContentScanner; print('✅ OK')"
```

### Cleanup after failed tests
```bash
# Remove stale loop devices
sudo losetup -D

# Remove stale LUKS mappers
sudo dmsetup ls
sudo cryptsetup close <mapper-name>

# Unmount stale mounts
sudo umount /tmp/pytest-*/mount
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Content Scanning Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Install system dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y cryptsetup-bin e2fsprogs util-linux
      
      - name: Install Python dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt
      
      - name: Run content scanning tests
        run: sudo python3 -m pytest tests/integration/test_content_scanning.py -v
```

## Adding New Tests

### Test Template

```python
@pytest.mark.integration
@pytest.mark.skipif(not CONTENT_VERIFICATION_AVAILABLE, reason="Content verification not available")
@pytest.mark.skipif(os.geteuid() != 0, reason="Requires root privileges")
class TestMyNewFeature:
    """Test description."""
    
    def test_my_scenario(self, content_scanning_config, temp_dir):
        """Test case description."""
        # Arrange
        d = daemon.Daemon(config_path=content_scanning_config)
        
        # Act
        # ... perform test actions
        
        # Assert
        assert expected_condition
```

### Best Practices

1. **Always cleanup** - Use try/finally for device cleanup
2. **Use fixtures** - Reuse `encrypted_usb_device`, `unencrypted_usb_device`
3. **Mark appropriately** - Use `@pytest.mark.integration` and skip conditions
4. **Test isolation** - Each test should be independent
5. **Clear assertions** - Use descriptive assertion messages

## Test Coverage

Current coverage areas:

- ✅ Encrypted USB device scanning
- ✅ Unencrypted USB device scanning (exempted users)
- ✅ Pattern detection (SSN, credit cards, API keys)
- ✅ Archive scanning (ZIP files)
- ✅ Large file performance
- ✅ Concurrent scanning
- ✅ FUSE manager integration

Future coverage needed:

- ⏳ Document scanning (PDF, DOCX, XLSX)
- ⏳ Other archive formats (TAR, 7Z, RAR)
- ⏳ Binary file handling
- ⏳ Symbolic link handling
- ⏳ FUSE remount on device removal
- ⏳ Progress callback verification
- ⏳ DBus signal emission

## Related Documentation

- [FUSE Implementation Guide](FUSE-OVERLAY-GUIDE.md)
- [Content Scanning Architecture](CONTENT-VERIFICATION-WHITEPAPER.md)
- [Group Exemptions](GROUP-EXEMPTIONS.md)
- [Testing Guide](TESTING.md)

## Support

For issues with tests:

1. Check [Troubleshooting](#troubleshooting) section above
2. Review test output for specific error messages
3. Check system logs: `sudo journalctl -xe`
4. Verify all dependencies installed
5. Run with `--tb=long` for full tracebacks

For test failures, include:
- Full test output
- Operating system and version
- Kernel version (`uname -r`)
- Python version (`python3 --version`)
- Installed package versions (`pip3 list`)

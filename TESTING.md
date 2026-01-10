# USB Enforcer Testing Guide

This document describes the comprehensive test suite for USB Enforcer, including unit tests, integration tests, and instructions for running tests locally and in CI/CD.

## Table of Contents

- [Overview](#overview)
- [Test Structure](#test-structure)
- [Prerequisites](#prerequisites)
- [Running Tests](#running-tests)
- [Test Categories](#test-categories)
- [Integration Test Details](#integration-test-details)
- [Writing New Tests](#writing-new-tests)
- [Continuous Integration](#continuous-integration)
- [Troubleshooting](#troubleshooting)

## Overview

The USB Enforcer test suite provides comprehensive coverage of:

- **Unit Tests**: Test individual components in isolation using mocks
- **Integration Tests**: Test actual encryption, enforcement, and device operations using loop devices
- **Code Quality**: Automated formatting, linting, and type checking

The test suite simulates USB devices using loop devices, allowing realistic testing without physical hardware.

## Test Structure

```
tests/
├── conftest.py              # Pytest configuration and shared fixtures
├── pytest.ini               # Pytest settings
├── unit/                    # Unit tests (no root required)
│   ├── test_classify.py     # Device classification tests
│   ├── test_config.py       # Configuration loading tests
│   ├── test_enforcer.py     # Enforcement policy tests
│   └── test_user_utils.py   # User/group utility tests
├── integration/             # Integration tests (requires root)
│   ├── test_encryption.py   # LUKS encryption tests
│   └── test_enforcement.py  # Policy enforcement tests
└── fixtures/
    └── loop_device_helper.py  # Helper script for loop device management
```

## Prerequisites

### System Dependencies

**For Unit Tests:**
```bash
# Debian/Ubuntu
sudo apt-get install python3-gi gir1.2-gtk-3.0 libgirepository1.0-dev

# Fedora/RHEL
sudo dnf install python3-gobject gtk3 gobject-introspection-devel
```

**For Integration Tests (requires root):**
```bash
# Debian/Ubuntu
sudo apt-get install cryptsetup parted e2fsprogs exfatprogs dosfstools

# Fedora/RHEL
sudo dnf install cryptsetup parted e2fsprogs exfatprogs dosfstools
```

### Python Dependencies

```bash
# Install runtime dependencies
pip install -r requirements.txt

# Install test dependencies
pip install -r requirements-test.txt
```

## Running Tests

### Run All Unit Tests

```bash
# No root required
pytest tests/unit/ -v
```

### Run All Integration Tests

```bash
# Requires root privileges
sudo pytest tests/integration/ -v -m integration
```

### Run Specific Test File

```bash
# Unit test
pytest tests/unit/test_classify.py -v

# Integration test (with root)
sudo pytest tests/integration/test_encryption.py -v
```

### Run Specific Test Function

```bash
pytest tests/unit/test_classify.py::TestDeviceClassification::test_classify_plaintext -v
```

### Run Tests with Coverage

```bash
# Unit tests with coverage
pytest tests/unit/ --cov=src/usb_enforcer --cov-report=html --cov-report=term

# View coverage report
open htmlcov/index.html  # or xdg-open on Linux
```

### Run All Tests (Unit + Integration)

```bash
# Run unit tests first (no root)
pytest tests/unit/ -v

# Then run integration tests (with root)
sudo -E env "PATH=$PATH" pytest tests/integration/ -v -m integration
```

## Test Categories

### Unit Tests (51 tests)

**Characteristics:**
- No root privileges required
- No external dependencies (mocked)
- Fast execution (<1 second)
- High code coverage

**What's Tested:**
- Device classification logic
- Configuration file parsing
- User/group membership checking
- Enforcement policy logic (mocked)
- Edge cases and error handling

**Example:**
```bash
pytest tests/unit/ -v
```

### Integration Tests (60+ tests)

**Characteristics:**
- **Requires root privileges**
- Uses loop devices to simulate USB storage
- Tests real encryption, formatting, mounting
- Slower execution (30-60 seconds)
- Tests actual system behavior

**What's Tested:**
- LUKS1/LUKS2 encryption on loop devices
- Read-only enforcement via sysfs
- Device formatting (ext4, exfat, vfat)
- Mounting and writing to encrypted devices
- Policy enforcement on real devices
- Device partition operations
- **Daemon initialization and lifecycle**
- **Secret socket communication**
- **D-Bus API method calls and signals**
- **Real-world usage workflows**
- **Multiple encryption/decryption cycles**
- **Error handling and edge cases**

**Example:**
```bash
sudo pytest tests/integration/test_encryption.py -v
sudo pytest tests/integration/test_crypto_engine.py -v
sudo pytest tests/integration/test_daemon.py -v
sudo pytest tests/integration/test_dbus_integration.py -v
```

## Integration Test Details

### Loop Device Testing

Integration tests use Linux loop devices to simulate USB drives:

```python
# Example from test
with loop_device(size_mb=100) as device:
    # Device is /dev/loopX
    # Format, encrypt, mount, test
    pass
# Automatic cleanup
```

### What Loop Devices Test

1. **Device Creation**: Create disk images and attach as loop devices
2. **Partitioning**: Create partition tables and partitions
3. **Formatting**: Format with various filesystems (ext4, exfat, vfat)
4. **Encryption**: LUKS1/LUKS2 encryption and unlocking
5. **Mounting**: Mount and write operations
6. **Read-Only**: Test sysfs-based read-only enforcement
7. **Policy Enforcement**: Apply actual enforcement policies

### Manual Loop Device Testing

You can also use the helper script directly:

```bash
# Create a plaintext loop device
sudo python3 tests/fixtures/loop_device_helper.py create --size 100 --fstype ext4

# Create an encrypted loop device
sudo python3 tests/fixtures/loop_device_helper.py create \
    --size 100 \
    --encrypt \
    --luks-version 2 \
    --fstype ext4 \
    --passphrase "test-password"

# Cleanup
sudo python3 tests/fixtures/loop_device_helper.py cleanup
```

### Testing Different Scenarios

```bash
# Test LUKS2 encryption
sudo pytest tests/integration/test_encryption.py::TestLUKSEncryption::test_encrypt_device_luks2 -v

# Test read-only enforcement
sudo pytest tests/integration/test_enforcement.py::TestReadOnlyEnforcement::test_set_partition_readonly -v

# Test plaintext device enforcement
sudo pytest tests/integration/test_enforcement.py::TestPolicyEnforcement::test_enforce_on_plaintext_partition -v
```

## Writing New Tests

### Unit Test Template

```python
"""tests/unit/test_mymodule.py"""
from unittest.mock import patch, MagicMock
import pytest
from usb_enforcer import mymodule


class TestMyFeature:
    """Test my feature."""
    
    def test_basic_functionality(self):
        """Test basic functionality."""
        result = mymodule.my_function("input")
        assert result == "expected"
    
    @patch('usb_enforcer.mymodule.external_call')
    def test_with_mock(self, mock_external):
        """Test with mocked external dependency."""
        mock_external.return_value = "mocked"
        result = mymodule.my_function()
        assert result == "mocked"
        mock_external.assert_called_once()
```

### Integration Test Template

```python
"""tests/integration/test_myfeature.py"""
import pytest


@pytest.mark.integration
class TestMyIntegrationFeature:
    """Integration tests for my feature."""
    
    def test_with_loop_device(self, loop_device, require_cryptsetup):
        """Test feature with loop device."""
        with loop_device(size_mb=100) as device:
            # Your test code here
            # Device will be cleaned up automatically
            pass
```

## Continuous Integration

### GitHub Actions

The test suite runs automatically on GitHub Actions:

- **Unit Tests**: Run on every push/PR (Python 3.10, 3.11, 3.12)
- **Integration Tests**: Run on every push/PR (may be flaky)
- **Code Quality**: Check formatting, linting, type hints
- **Package Building**: Test DEB/RPM package creation

See `.github/workflows/test.yml` for details.

### Local CI Simulation

Run the same checks as CI locally:

```bash
# Code formatting
black --check src/ tests/

# Import sorting
isort --check-only src/ tests/

# Linting
flake8 src/ tests/

# Type checking
mypy src/

# All tests
pytest tests/unit/ -v
sudo pytest tests/integration/ -v -m integration
```

## Troubleshooting

### Common Issues

#### "Permission denied" on Integration Tests

**Problem**: Integration tests need root privileges
```
PermissionError: [Errno 1] Operation not permitted
```

**Solution**: Run with sudo
```bash
sudo pytest tests/integration/ -v -m integration
```

#### Loop Device Not Found

**Problem**: Loop device didn't appear after creation
```
AssertionError: Partition /dev/loop0p1 not found
```

**Solution**: Wait for udev or use partprobe
```bash
sudo partprobe /dev/loop0
```

#### Import Errors

**Problem**: Module not found
```
ModuleNotFoundError: No module named 'usb_enforcer'
```

**Solution**: Install in development mode
```bash
pip install -e .
```

#### Cryptsetup Not Found

**Problem**: cryptsetup command missing
```
FileNotFoundError: [Errno 2] No such file or directory: 'cryptsetup'
```

**Solution**: Install cryptsetup
```bash
# Debian/Ubuntu
sudo apt-get install cryptsetup

# Fedora/RHEL
sudo dnf install cryptsetup
```

### Test Isolation

Each test should clean up after itself. If tests leave artifacts:

```bash
# List loop devices
losetup -a

# Detach all loop devices
sudo losetup -D

# Remove test files
sudo rm -rf /tmp/usb-enforcer-tests/
```

### Debugging Tests

Run with verbose output and show print statements:

```bash
pytest tests/unit/test_classify.py -v -s
```

Run with debugger on failure:

```bash
pytest tests/unit/test_classify.py --pdb
```

Run specific test with maximum verbosity:

```bash
pytest tests/unit/test_classify.py::TestDeviceClassification::test_classify_plaintext -vvv
```

## Test Coverage Goals

| Module | Current Coverage | Target |
|--------|-----------------|--------|
| classify.py | 95%+ | 100% |
| config.py | 95%+ | 100% |
| user_utils.py | 90%+ | 95% |
| enforcer.py | 85%+ | 90% |
| crypto_engine.py | 70%+ | 85% |
| daemon.py | 60%+ | 75% |

## Performance Benchmarks

Typical test execution times:

- **Unit tests**: ~2-5 seconds (all tests)
- **Integration tests**: ~30-60 seconds (all tests)
- **Single encryption test**: ~5-10 seconds
- **Single enforcement test**: ~3-5 seconds

## Contributing Tests

When adding new features:

1. **Write unit tests first** (TDD approach)
2. **Add integration tests** for system-level behavior
3. **Aim for 80%+ code coverage**
4. **Test both success and failure cases**
5. **Use descriptive test names**
6. **Add docstrings** explaining what's tested

Example PR checklist:
- [ ] Unit tests added
- [ ] Integration tests added (if applicable)
- [ ] All tests pass locally
- [ ] Code coverage maintained or improved
- [ ] Tests documented in docstrings

## Additional Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [Python unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
- [Loop device testing guide](https://www.kernel.org/doc/html/latest/admin-guide/devices.html)

## Questions?

If you have questions about testing, please:
1. Check this document first
2. Review existing tests for examples
3. Open an issue on GitHub
4. Contact the maintainers

---

**Happy Testing! 🧪**

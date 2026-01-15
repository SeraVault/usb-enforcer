# USB Enforcer Tests

This directory contains the comprehensive test suite for USB Enforcer.

## Quick Start

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run unit tests (no root required)
make test
# or
./run-tests.sh unit

# Run integration tests (requires root)
sudo make test-integration
# or
sudo ./run-tests.sh integration

# Run with coverage
make test-coverage

# Run all tests
sudo make test-all
```

## Directory Structure

- **`unit/`** - Unit tests (mocked, no root required)
- **`integration/`** - Integration tests (loop devices, requires root)
- **`fixtures/`** - Helper scripts and test utilities
- **`conftest.py`** - Pytest configuration and shared fixtures

## Test Types

### Unit Tests (`tests/unit/`)

Test individual components in isolation:
- `test_classify.py` - Device classification logic
- `test_config.py` - Configuration parsing
- `test_enforcer.py` - Enforcement policies
- `test_user_utils.py` - User/group utilities

**Run:** `pytest tests/unit/ -v`

### Integration Tests (`tests/integration/`)

Test actual system operations using loop devices:
- `test_encryption.py` - LUKS encryption operations
- `test_enforcement.py` - Policy enforcement on real devices

**Run:** `sudo pytest tests/integration/ -v -m integration`

## Writing Tests

See [TESTING.md](../docs/TESTING.md) for comprehensive documentation on:
- Writing new tests
- Using fixtures
- Testing with loop devices
- Debugging tests
- Contributing guidelines

## Quick Examples

### Run Specific Test
```bash
pytest tests/unit/test_classify.py::TestDeviceClassification::test_classify_plaintext -v
```

### Run with Debug Output
```bash
pytest tests/unit/test_config.py -v -s
```

### Run with Coverage
```bash
pytest tests/unit/ --cov=src/usb_enforcer --cov-report=html
```

## Requirements

### Unit Tests
- Python 3.10+
- pytest
- pytest-cov
- pytest-mock

### Integration Tests (additional)
- Root privileges
- cryptsetup
- parted
- e2fsprogs
- losetup

## CI/CD

Tests run automatically on GitHub Actions:
- Unit tests on Python 3.10, 3.11, 3.12
- Integration tests on Ubuntu latest
- Code quality checks (black, flake8, isort, mypy)

See `.github/workflows/test.yml` for details.

## Documentation

For complete testing documentation, see:
- [TESTING.md](../docs/TESTING.md) - Comprehensive testing guide
- [conftest.py](conftest.py) - Available fixtures
- Individual test files for examples

## Support

Questions? Check:
1. [TESTING.md](../docs/TESTING.md)
2. Existing test examples
3. Open an issue on GitHub

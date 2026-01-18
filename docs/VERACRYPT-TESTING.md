# VeraCrypt Testing Guide

This document describes how to run the VeraCrypt-related tests for USB Enforcer.

## Test Files

### Integration Tests
- **File**: `tests/integration/test_veracrypt.py`
- **Requires**: Root privileges, VeraCrypt installed, loop device support
- **Tests**: Real VeraCrypt operations on loop devices

### Unit Tests
- **File**: `tests/unit/test_crypto_engine.py`
- **Requires**: No special privileges (uses mocks)
- **Tests**: Logic and command construction for VeraCrypt operations

## Running Tests

### All VeraCrypt Integration Tests

```bash
# Requires root and VeraCrypt installed
sudo pytest tests/integration/test_veracrypt.py -v
```

### Specific VeraCrypt Tests

```bash
# Test VeraCrypt volume detection
sudo pytest tests/integration/test_veracrypt.py::TestVeraCryptEncryption::test_veracrypt_version_detection -v

# Test VeraCrypt encryption workflow
sudo pytest tests/integration/test_veracrypt.py::TestVeraCryptEncryption::test_encrypt_device_veracrypt -v

# Test VeraCrypt unlock
sudo pytest tests/integration/test_veracrypt.py::TestVeraCryptEncryption::test_unlock_veracrypt -v

# Test interoperability (LUKS vs VeraCrypt detection)
sudo pytest tests/integration/test_veracrypt.py::TestVeraCryptInteroperability -v
```

### Unit Tests (No Root Required)

```bash
# Run all VeraCrypt unit tests
pytest tests/unit/test_crypto_engine.py::TestVeraCryptVersion -v
pytest tests/unit/test_crypto_engine.py::TestUnlockVeraCrypt -v
pytest tests/unit/test_crypto_engine.py::TestEncryptDevice::test_encrypt_device_veracrypt_workflow -v
pytest tests/unit/test_crypto_engine.py::TestEncryptDevice::test_encrypt_device_veracrypt_not_installed -v
```

### Run All Tests Together

```bash
# Integration + Unit tests for both LUKS and VeraCrypt
sudo pytest tests/integration/test_encryption.py tests/integration/test_veracrypt.py -v
pytest tests/unit/test_crypto_engine.py -v
```

## Test Coverage

### Integration Tests Cover:

1. **VeraCrypt Detection**
   - Detecting VeraCrypt volumes
   - Rejecting plaintext devices
   - Not false-positive on LUKS devices

2. **VeraCrypt Encryption**
   - Creating VeraCrypt volumes
   - Encrypting with different filesystems (ext4, exfat)
   - Setting filesystem labels
   - Error handling

3. **VeraCrypt Unlock/Lock**
   - Unlocking VeraCrypt volumes
   - Closing/dismounting volumes
   - Mount point management

4. **Interoperability**
   - LUKS not detected as VeraCrypt
   - VeraCrypt not detected as LUKS
   - Both working independently

### Unit Tests Cover:

1. **Command Construction**
   - VeraCrypt version detection logic
   - Unlock command with stdin password
   - Dismount commands
   - Create volume commands

2. **Workflow Logic**
   - encrypt_device with VeraCrypt type
   - Error handling when VeraCrypt not installed
   - Mount point creation
   - Mapper device detection

3. **Edge Cases**
   - VeraCrypt not installed
   - No mapper devices found
   - Fallback to mount point

## Prerequisites

### For Integration Tests

1. **Root Access**
   ```bash
   sudo -v
   ```

2. **VeraCrypt Installed**
   ```bash
   veracrypt --version
   # Should output: VeraCrypt 1.26.x
   ```

3. **Loop Device Support**
   ```bash
   lsmod | grep loop
   # Should show loop module loaded
   ```

### For Unit Tests

Only Python packages required (no special system requirements):
```bash
pip install pytest pytest-cov
```

## Test Skipping Behavior

Tests will automatically skip if requirements are not met:

- **No root**: `TestVeraCryptEncryption` tests skipped
- **No VeraCrypt**: Tests with `require_veracrypt` fixture skipped
- **No loop devices**: Tests with `loop_device` fixture skipped

Example output when VeraCrypt not installed:
```
SKIPPED [1] tests/conftest.py:95: This test requires veracrypt (install from https://www.veracrypt.fr)
```

## Continuous Integration

For CI/CD pipelines without VeraCrypt:

```bash
# Run only non-VeraCrypt tests
pytest tests/unit/ -v -k "not veracrypt"
pytest tests/integration/test_encryption.py -v  # LUKS only
```

## Troubleshooting

### Test Hangs or Prompts for Password

**Issue**: VeraCrypt prompting for password interactively

**Solution**: Ensure tests use `--stdin` flag and pass password via `input_data`

### "Device or resource busy" Errors

**Issue**: VeraCrypt volumes not properly dismounted

**Solution**: 
```bash
# List all VeraCrypt volumes
veracrypt --text --list

# Dismount all
veracrypt --text --dismount
```

### Loop Device Cleanup

**Issue**: Loop devices not released after tests

**Solution**:
```bash
# List loop devices
losetup -a

# Remove specific device
sudo losetup -d /dev/loop0
```

## Example Test Run

```bash
$ sudo pytest tests/integration/test_veracrypt.py -v

tests/integration/test_veracrypt.py::TestVeraCryptEncryption::test_veracrypt_version_detection PASSED
tests/integration/test_veracrypt.py::TestVeraCryptEncryption::test_veracrypt_version_plaintext PASSED
tests/integration/test_veracrypt.py::TestVeraCryptEncryption::test_veracrypt_version_luks PASSED
tests/integration/test_veracrypt.py::TestVeraCryptEncryption::test_encrypt_device_veracrypt PASSED
tests/integration/test_veracrypt.py::TestVeraCryptEncryption::test_unlock_veracrypt PASSED
tests/integration/test_veracrypt.py::TestVeraCryptEncryption::test_close_veracrypt_mapper PASSED
tests/integration/test_veracrypt.py::TestVeraCryptEncryption::test_format_veracrypt_device PASSED
tests/integration/test_veracrypt.py::TestVeraCryptEncryption::test_veracrypt_with_label PASSED
tests/integration/test_veracrypt.py::TestVeraCryptInteroperability::test_luks_not_detected_as_veracrypt PASSED
tests/integration/test_veracrypt.py::TestVeraCryptInteroperability::test_veracrypt_not_detected_as_luks PASSED

========================================= 10 passed in 45.23s =========================================
```

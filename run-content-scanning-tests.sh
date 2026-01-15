#!/bin/bash
# Test runner for content scanning integration tests
# Requires root privileges for creating virtual USB devices

set -e

echo "========================================="
echo "Content Scanning Integration Test Runner"
echo "========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: These tests require root privileges (for loopback devices and cryptsetup)"
    echo "Please run with: sudo $0"
    exit 1
fi

# Check dependencies
echo "Checking dependencies..."
MISSING_DEPS=()

command -v pytest >/dev/null 2>&1 || MISSING_DEPS+=("pytest")
command -v losetup >/dev/null 2>&1 || MISSING_DEPS+=("losetup")
command -v cryptsetup >/dev/null 2>&1 || MISSING_DEPS+=("cryptsetup")
command -v mkfs.ext4 >/dev/null 2>&1 || MISSING_DEPS+=("e2fsprogs")

if [ ${#MISSING_DEPS[@]} -ne 0 ]; then
    echo "ERROR: Missing required dependencies:"
    for dep in "${MISSING_DEPS[@]}"; do
        echo "  - $dep"
    done
    echo ""
    echo "Install with:"
    echo "  Fedora/RHEL: dnf install python3-pytest util-linux cryptsetup e2fsprogs"
    echo "  Ubuntu/Debian: apt install python3-pytest util-linux cryptsetup e2fsprogs"
    exit 1
fi

echo "✅ All dependencies found"
echo ""

# Install Python test dependencies if needed
echo "Installing Python test dependencies..."
pip3 install -q -r requirements-test.txt 2>/dev/null || true

echo ""
echo "Running content scanning integration tests..."
echo "=============================================="
echo ""

# Run tests with verbose output
python3 -m pytest tests/integration/test_content_scanning.py \
    -v \
    --tb=short \
    --color=yes \
    "$@"

exit_code=$?

echo ""
echo "=============================================="
if [ $exit_code -eq 0 ]; then
    echo "✅ All tests passed!"
else
    echo "❌ Some tests failed (exit code: $exit_code)"
fi
echo "=============================================="

exit $exit_code

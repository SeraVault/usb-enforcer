#!/usr/bin/env bash
# Download Python dependencies as wheels for bundling in RPM
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
REPO_ROOT="$(realpath "$SCRIPT_DIR/..")"
WHEELS_DIR="${REPO_ROOT}/wheels"

echo "Downloading Python dependencies as wheels..."

# Clean and create wheels directory
rm -rf "$WHEELS_DIR"
mkdir -p "$WHEELS_DIR"

# Download wheels for the target platform
# Use --platform and --only-binary to get platform-specific wheels
python3 -m pip download \
    --dest "$WHEELS_DIR" \
    --no-deps \
    "pyudev>=0.24.0" \
    "pydbus>=0.6.0" \
    "typing-extensions>=4.8.0"

echo ""
echo "Downloaded wheels to: $WHEELS_DIR"
ls -lh "$WHEELS_DIR"

echo ""
echo "Creating python-deps.tar.gz..."
cd "$REPO_ROOT"
tar czf python-deps.tar.gz wheels/
rm -rf wheels/

echo "Created python-deps.tar.gz ($(du -h python-deps.tar.gz | cut -f1))"
echo ""
echo "Copy this file to ~/rpmbuild/SOURCES/ when building the bundled RPM"

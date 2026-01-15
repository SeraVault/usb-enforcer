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
    "typing-extensions>=4.8.0" \
    "python-magic>=0.4.27" \
    "pdfplumber>=0.10.0" \
    "python-docx>=1.0.0" \
    "openpyxl>=3.1.0" \
    "python-pptx>=0.6.0" \
    "odfpy>=1.4.0" \
    "py7zr>=0.20.0" \
    "rarfile>=4.1" \
    "fusepy>=3.0.1" \
    "xlrd>=2.0.0" \
    "olefile>=0.46" \
    "extract-msg>=0.41.0" \
    "striprtf>=0.0.26"

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

#!/usr/bin/env bash
set -euo pipefail

# Update Debian changelog files with version from VERSION file

VERSION_FILE="${1:-VERSION}"
CHANGELOG_FILE="${2:-debian/changelog}"

if [[ ! -f "$VERSION_FILE" ]]; then
    echo "Error: VERSION file not found: $VERSION_FILE" >&2
    exit 1
fi

if [[ ! -f "$CHANGELOG_FILE" ]]; then
    echo "Error: Changelog file not found: $CHANGELOG_FILE" >&2
    exit 1
fi

# Read version from VERSION file
VERSION=$(tr -d '[:space:]' < "$VERSION_FILE")

if [[ -z "$VERSION" ]]; then
    echo "Error: VERSION file is empty" >&2
    exit 1
fi

# Extract package name from first line of changelog
PACKAGE_NAME=$(head -n1 "$CHANGELOG_FILE" | cut -d' ' -f1)

# Update the version in the first line of the changelog
# Format: package-name (version-release) distribution; urgency=level
sed -i "1s/^${PACKAGE_NAME} ([^)]*) /${PACKAGE_NAME} (${VERSION}-1) /" "$CHANGELOG_FILE"

echo "Updated $CHANGELOG_FILE to version $VERSION"

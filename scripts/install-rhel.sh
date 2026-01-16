#!/usr/bin/env bash
# Backward-compatible wrapper for RHEL/Fedora-family install.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
exec env DISTRO_FAMILY=rhel "${SCRIPT_DIR}/install.sh" "$@"

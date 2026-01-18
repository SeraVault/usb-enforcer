#!/usr/bin/env bash
# Legacy wrapper for RHEL/Fedora uninstall.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
exec "${SCRIPT_DIR}/uninstall.sh" "$@"

#!/usr/bin/env bash
# Legacy wrapper for Debian/Ubuntu/Mint uninstall.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
exec "${SCRIPT_DIR}/uninstall.sh" "$@"

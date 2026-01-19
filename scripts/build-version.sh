#!/usr/bin/env bash
set -euo pipefail

BASE_VERSION_FILE="${BASE_VERSION_FILE:-VERSION}"

# If BUILD_VERSION is set explicitly, use it
if [[ -n "${BUILD_VERSION:-}" ]]; then
  echo "${BUILD_VERSION}"
  exit 0
fi

# Read version from VERSION file if it exists
if [[ -f "${BASE_VERSION_FILE}" ]]; then
  base_version="$(tr -d '[:space:]' < "${BASE_VERSION_FILE}")"
  # If version is not empty, use it directly (no timestamp for releases)
  if [[ -n "${base_version}" ]]; then
    echo "${base_version}"
    exit 0
  fi
fi

# Fallback for development (should rarely be used)
base_version="1.0.0"
timestamp="$(date -u +"%Y%m%d%H%M%S")"
echo "${base_version}.post${timestamp}"

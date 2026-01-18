#!/usr/bin/env bash
set -euo pipefail

BASE_VERSION_FILE="${BASE_VERSION_FILE:-VERSION}"

if [[ -n "${BUILD_VERSION:-}" ]]; then
  echo "${BUILD_VERSION}"
  exit 0
fi

base_version="1.0.0"
if [[ -f "${BASE_VERSION_FILE}" ]]; then
  base_version="$(tr -d '[:space:]' < "${BASE_VERSION_FILE}")"
fi

timestamp="$(date -u +"%Y%m%d%H%M%S")"
echo "${base_version}.post${timestamp}"

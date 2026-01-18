#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <build_dir> <version>" >&2
  exit 1
fi

build_dir="$1"
version="$2"

if [[ ! -d "${build_dir}" ]]; then
  echo "Build directory not found: ${build_dir}" >&2
  exit 1
fi

replace_version() {
  local file="$1"
  local pattern="$2"
  local replacement="$3"
  if [[ -f "${file}" ]]; then
    perl -pi -e "s/${pattern}/${replacement}/" "${file}"
  fi
}

replace_version "${build_dir}/setup.py" 'version="[^"]+"' "version=\"${version}\""
replace_version "${build_dir}/src/usb_enforcer/content_verification/__init__.py" "__version__ = '[^']+'" "__version__ = '${version}'"
replace_version "${build_dir}/src/usb_enforcer/encryption/__init__.py" "__version__ = '[^']+'" "__version__ = '${version}'"

replace_version "${build_dir}/rpm/usb-enforcer.spec" '^Version:\s+.*$' "Version:        ${version}"
replace_version "${build_dir}/rpm-bundled/usb-enforcer-bundled.spec" '^Version:\s+.*$' "Version:        ${version}"

replace_version "${build_dir}/debian/changelog" '^\w+ \([^)]+\)' "usb-enforcer (${version}-1)"
replace_version "${build_dir}/debian-bundled/changelog" '^\w+ \([^)]+\)' "usb-enforcer-bundled (${version}-1)"
replace_version "${build_dir}/debian-admin/changelog" '^\w+ \([^)]+\)' "usb-enforcer-admin (${version}-1)"

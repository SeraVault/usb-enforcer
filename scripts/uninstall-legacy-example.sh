#!/usr/bin/env bash
# Temporary cleanup of legacy org.example artifacts.
set -euo pipefail

TARGETS=(
  "/etc/dbus-1/system.d/org.example.UsbEncryptionEnforcer.conf"
)

log() { echo "[uninstall-legacy] $*"; }

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run as root to remove system dbus policy." >&2
  exit 1
fi

for path in "${TARGETS[@]}"; do
  if [[ -f "$path" ]]; then
    log "Removing $path"
    rm -f "$path"
  else
    log "Not found: $path (skipping)"
  fi
done

log "Reloading dbus/systemd to drop legacy policy"
systemctl restart dbus || log "Warning: could not restart dbus; please reboot or restart manually"
systemctl daemon-reload || true

log "Legacy org.example artifacts removed (if present)."

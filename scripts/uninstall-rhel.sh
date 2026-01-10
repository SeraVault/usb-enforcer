#!/usr/bin/env bash
# Uninstall USB Encryption Enforcer (DLP) from RHEL/Fedora-family systems.
set -euo pipefail

PREFIX="${PREFIX:-/usr}"
LIBDIR="${LIBDIR:-${PREFIX}/lib/usb-enforcer}"
LIBEXEC="${LIBEXEC:-${PREFIX}/libexec}"
CONFIG_DIR="${CONFIG_DIR:-/etc/usb-enforcer}"
SYSTEMD_SYSTEM_DIR="${SYSTEMD_SYSTEM_DIR:-/etc/systemd/system}"
SYSTEMD_USER_DIR="${SYSTEMD_USER_DIR:-/etc/systemd/user}"
POLKIT_DIR="${POLKIT_DIR:-/etc/polkit-1/rules.d}"
UDEV_DIR="${UDEV_DIR:-/etc/udev/rules.d}"
DBUS_DIR="${DBUS_DIR:-/etc/dbus-1/system.d}"

log() {
  echo "[uninstall] $*"
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "This uninstaller must run as root." >&2
    exit 1
  fi
}

stop_and_disable_services() {
  log "Stopping and disabling system daemon"
  systemctl disable --now usb-enforcerd || log "Warning: daemon service not active"
  
  log "Disabling user notification bridge for all users"
  rm -f "${SYSTEMD_USER_DIR}/default.target.wants/usb-enforcer-ui.service"
  
  # Stop user service for the user who ran sudo
  if [[ -n "${SUDO_USER:-}" ]] && [[ "${SUDO_USER:-}" != "root" ]]; then
    log "Stopping user service for $SUDO_USER"
    sudo -u "$SUDO_USER" XDG_RUNTIME_DIR="/run/user/$(id -u "$SUDO_USER")" \
      systemctl --user disable --now usb-enforcer-ui 2>/dev/null || log "Warning: user service not running for $SUDO_USER"
  else
    log "Per-user stop requires: systemctl --user disable --now usb-enforcer-ui"
  fi
}

remove_systemd_units() {
  log "Removing systemd units and drop-ins"
  rm -f "${SYSTEMD_SYSTEM_DIR}/usb-enforcerd.service"
  rm -rf "${SYSTEMD_SYSTEM_DIR}/usb-enforcerd.service.d"
  rm -f "${SYSTEMD_USER_DIR}/usb-enforcer-ui.service"
  rm -rf "${SYSTEMD_USER_DIR}/usb-enforcer-ui.service.d"
}

remove_config_rules() {
  log "Removing configuration and policy files"
  rm -f "${UDEV_DIR}/49-usb-enforcer.rules"
  rm -f "${UDEV_DIR}/80-udisks2-usb-enforcer.rules"
  rm -f "${POLKIT_DIR}/49-usb-enforcer.rules"
  rm -f "${DBUS_DIR}/org.seravault.UsbEnforcer.conf"
  
  # Optionally remove config directory (prompting user)
  if [[ -d "${CONFIG_DIR}" ]]; then
    log "Configuration directory ${CONFIG_DIR} contains user settings"
    read -p "Remove configuration directory? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      log "Removing ${CONFIG_DIR}"
      rm -rf "${CONFIG_DIR}"
    else
      log "Keeping ${CONFIG_DIR}"
    fi
  fi
}

remove_scripts() {
  log "Removing executable scripts"
  rm -f "${LIBEXEC}/usb-enforcerd"
  rm -f "${LIBEXEC}/usb-enforcer-helper"
  rm -f "${LIBEXEC}/usb-enforcer-ui"
  rm -f "${LIBEXEC}/usb-enforcer-wizard"
}

remove_python_bits() {
  log "Removing Python package and virtualenv"
  rm -rf "${LIBDIR}"
}

reload_services() {
  log "Reloading systemd and udev"
  systemctl daemon-reload
  udevadm control --reload
  
  # Reload user systemd for the user who ran sudo
  if [[ -n "${SUDO_USER:-}" ]] && [[ "${SUDO_USER:-}" != "root" ]]; then
    log "Reloading user systemd for $SUDO_USER"
    sudo -u "$SUDO_USER" XDG_RUNTIME_DIR="/run/user/$(id -u "$SUDO_USER")" \
      systemctl --user daemon-reload 2>/dev/null || true
  fi
}

main() {
  require_root
  stop_and_disable_services
  remove_systemd_units
  remove_config_rules
  remove_scripts
  remove_python_bits
  reload_services
  log "Uninstall complete."
  log "Note: Run 'systemctl --user daemon-reload' in any active user sessions"
}

main "$@"

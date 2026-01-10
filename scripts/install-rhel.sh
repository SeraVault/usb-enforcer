#!/usr/bin/env bash
# Install USB Enforcer (DLP) on RHEL/Fedora-family systems.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
REPO_ROOT="$(realpath "$SCRIPT_DIR/..")"

PREFIX="${PREFIX:-/usr}"
LIBDIR="${LIBDIR:-${PREFIX}/lib/usb-enforcer}"
LIBEXEC="${LIBEXEC:-${PREFIX}/libexec}"
CONFIG_DIR="${CONFIG_DIR:-/etc/usb-enforcer}"
SYSTEMD_SYSTEM_DIR="${SYSTEMD_SYSTEM_DIR:-/etc/systemd/system}"
SYSTEMD_USER_DIR="${SYSTEMD_USER_DIR:-/etc/systemd/user}"
POLKIT_DIR="${POLKIT_DIR:-/etc/polkit-1/rules.d}"
UDEV_DIR="${UDEV_DIR:-/etc/udev/rules.d}"
DBUS_DIR="${DBUS_DIR:-/etc/dbus-1/system.d}"
VENV_DIR="${VENV_DIR:-${LIBDIR}/.venv}"

PYTHON_BIN="${PYTHON_BIN:-python3}"

log() {
  echo "[install] $*"
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "This installer must run as root." >&2
    exit 1
  fi
}

create_dirs() {
  install -d "$LIBDIR" "$LIBEXEC" "$CONFIG_DIR" "$SYSTEMD_SYSTEM_DIR" "$SYSTEMD_USER_DIR" "$POLKIT_DIR" "$UDEV_DIR" "$DBUS_DIR"
  install -d "${SYSTEMD_SYSTEM_DIR}/usb-enforcerd.service.d"
  install -d "${SYSTEMD_USER_DIR}/usb-enforcer-ui.service.d"
}

install_python_bits() {
  log "Copying Python package to ${LIBDIR}"
  rm -rf "${LIBDIR}/usb_enforcer"
  cp -r "${REPO_ROOT}/src/usb_enforcer" "${LIBDIR}/"
}

install_scripts() {
  install -m 0755 "${REPO_ROOT}/scripts/usb-enforcerd" "${LIBEXEC}/"
  install -m 0755 "${REPO_ROOT}/scripts/usb-enforcer-helper" "${LIBEXEC}/"
  install -m 0755 "${REPO_ROOT}/scripts/usb-enforcer-ui" "${LIBEXEC}/"
  install -m 0755 "${REPO_ROOT}/scripts/usb-enforcer-wizard" "${LIBEXEC}/"
}

install_config_rules() {
  if [[ ! -f "${CONFIG_DIR}/config.toml" ]]; then
    install -m 0644 "${REPO_ROOT}/deploy/config.toml.sample" "${CONFIG_DIR}/config.toml"
  fi
  install -m 0644 "${REPO_ROOT}/deploy/udev/49-usb-enforcer.rules" "${UDEV_DIR}/"
  install -m 0644 "${REPO_ROOT}/deploy/udev/80-udisks2-usb-enforcer.rules" "${UDEV_DIR}/"
  install -m 0644 "${REPO_ROOT}/deploy/polkit/49-usb-enforcer.rules" "${POLKIT_DIR}/"
  install -m 0644 "${REPO_ROOT}/deploy/dbus/org.seravault.UsbEnforcer.conf" "${DBUS_DIR}/"
}

install_systemd_units() {
  install -m 0644 "${REPO_ROOT}/deploy/systemd/usb-enforcerd.service" "${SYSTEMD_SYSTEM_DIR}/"
  install -m 0644 "${REPO_ROOT}/deploy/systemd/usb-enforcer-ui.service" "${SYSTEMD_USER_DIR}/"

  cat > "${SYSTEMD_SYSTEM_DIR}/usb-enforcerd.service.d/env.conf" <<'EOF'
[Service]
Environment=PYTHONPATH=/usr/lib/usb-enforcer
Environment=PATH=/usr/lib/usb-enforcer/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
EOF

  cat > "${SYSTEMD_USER_DIR}/usb-enforcer-ui.service.d/env.conf" <<'EOF'
[Service]
Environment=PYTHONPATH=/usr/lib/usb-enforcer
Environment=PATH=/usr/lib/usb-enforcer/.venv/bin:/usr/local/bin:/usr/bin
EOF
}

setup_venv() {
  log "Creating virtualenv at ${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  # shellcheck disable=SC1090
  source "${VENV_DIR}/bin/activate"
  pip install --upgrade pip
  pip install -r "${REPO_ROOT}/requirements.txt"
}

reload_services() {
  log "Reloading systemd and udev"
  systemctl daemon-reload
  udevadm control --reload
  log "Enable and start daemon: systemctl enable --now usb-enforcerd"
  systemctl enable --now usb-enforcerd
  log "Enabling user notification bridge for all users via default.target.wants"
  install -d "${SYSTEMD_USER_DIR}/default.target.wants"
  ln -sf "${SYSTEMD_USER_DIR}/usb-enforcer-ui.service" "${SYSTEMD_USER_DIR}/default.target.wants/usb-enforcer-ui.service"
  
  # Start user service for the user who ran sudo
  if [[ -n "$SUDO_USER" ]] && [[ "$SUDO_USER" != "root" ]]; then
    log "Starting user service for $SUDO_USER"
    sudo -u "$SUDO_USER" XDG_RUNTIME_DIR="/run/user/$(id -u "$SUDO_USER")" \
      systemctl --user daemon-reload
    sudo -u "$SUDO_USER" XDG_RUNTIME_DIR="/run/user/$(id -u "$SUDO_USER")" \
      systemctl --user enable --now usb-enforcer-ui
  else
    log "Per-user start occurs on next login; to start immediately, run: systemctl --user daemon-reload && systemctl --user enable --now usb-enforcer-ui"
  fi
}

main() {
  require_root
  require_cmd cryptsetup
  require_cmd udevadm
  require_cmd systemctl
  # UI notifications; best-effort
  if ! command -v notify-send >/dev/null 2>&1; then
    log "notify-send not found; user notifications may not display"
  fi
  create_dirs
  install_python_bits
  install_scripts
  install_config_rules
  install_systemd_units
  setup_venv
  reload_services
  log "Install complete."
}

main "$@"

#!/bin/bash
# Uninstallation script for USB Enforcer Admin GUI

set -e

echo "===================================="
echo "USB Enforcer Admin GUI - Uninstaller"
echo "===================================="
echo

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)" 
   exit 1
fi

echo "This will remove USB Enforcer Admin GUI from your system."
echo "Configuration files (/etc/usb-enforcer/) will NOT be removed."
echo
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Uninstallation cancelled."
    exit 0
fi

echo
echo "Removing USB Enforcer Admin GUI..."

# Remove admin directory and venv
rm -rf /usr/lib/usb-enforcer-admin

# Remove installed files
rm -f /usr/bin/usb-enforcer-admin
rm -f /usr/share/applications/usb-enforcer-admin.desktop
rm -f /usr/share/polkit-1/actions/49-usb-enforcer-admin.policy
rm -f /usr/share/usb-enforcer/config.toml.sample
rm -rf /usr/share/doc/usb-enforcer

# Remove Python package (only if installed system-wide)
python3 -m pip uninstall -y usb-enforcer-admin 2>/dev/null || true

# Update desktop database
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications/ 2>/dev/null || true
fi

echo
echo "===================================="
echo "Uninstallation completed!"
echo "===================================="
echo
echo "Configuration files remain at: /etc/usb-enforcer/"
echo "To remove configuration: sudo rm -rf /etc/usb-enforcer/"
echo

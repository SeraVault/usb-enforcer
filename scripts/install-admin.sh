#!/bin/bash
# Installation script for USB Enforcer Admin GUI

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==================================="
echo "USB Enforcer Admin GUI - Installer"
echo "==================================="
echo

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)" 
   exit 1
fi

# Detect distribution
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO=$ID
    DISTRO_VERSION=$VERSION_ID
else
    echo "Cannot detect distribution. /etc/os-release not found."
    exit 1
fi

echo "Detected distribution: $DISTRO $DISTRO_VERSION"
echo

# Install system dependencies
echo "Installing system dependencies..."
case "$DISTRO" in
    ubuntu|debian|linuxmint|pop)
        apt-get update
        apt-get install -y \
            python3 \
            python3-pip \
            python3-toml \
            gir1.2-gtk-4.0 \
            gir1.2-adw-1 \
            python3-gi \
            python3-gi-cairo \
            policykit-1
        ;;
    fedora|rhel|centos|almalinux|rocky)
        dnf install -y \
            python3 \
            python3-pip \
            python3-toml \
            gtk4 \
            libadwaita \
            python3-gobject \
            polkit
        ;;
    *)
        echo "Unsupported distribution: $DISTRO"
        echo "Please install dependencies manually:"
        echo "  - Python 3.8+"
        echo "  - python3-toml"
        echo "  - GTK4"
        echo "  - libadwaita"
        echo "  - python3-gobject"
        echo "  - polkit"
        exit 1
        ;;
esac

echo
echo "Installing USB Enforcer Admin GUI..."

# Create dedicated admin directory and venv
ADMIN_DIR="/usr/lib/usb-enforcer-admin"
mkdir -p "$ADMIN_DIR"

echo "Creating virtual environment for admin GUI..."
python3 -m venv --system-site-packages "$ADMIN_DIR/.venv"

# Activate venv and install minimal dependencies
source "$ADMIN_DIR/.venv/bin/activate"
pip install --upgrade pip

# Install only toml if needed (Python 3.11+ has tomllib built-in)
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [ "$(python3 -c 'import sys; print(1 if sys.version_info >= (3,11) else 0)')" = "0" ]; then
    echo "Installing toml library for Python < 3.11..."
    pip install toml
else
    echo "Using built-in tomllib (Python 3.11+)"
fi

# Copy admin module to dedicated directory
mkdir -p "$ADMIN_DIR/usb_enforcer/ui"
cp -r "$PROJECT_ROOT/src/usb_enforcer/ui/admin.py" "$ADMIN_DIR/usb_enforcer/ui/"
touch "$ADMIN_DIR/usb_enforcer/__init__.py"
touch "$ADMIN_DIR/usb_enforcer/ui/__init__.py"

deactivate

# Install admin script
install -D -m 755 scripts/usb-enforcer-admin /usr/bin/usb-enforcer-admin

# Install desktop file
install -D -m 644 deploy/desktop/usb-enforcer-admin.desktop /usr/share/applications/usb-enforcer-admin.desktop

# Install polkit policy
install -D -m 644 deploy/polkit/49-usb-enforcer-admin.policy /usr/share/polkit-1/actions/49-usb-enforcer-admin.policy

# Install sample config
install -D -m 644 deploy/config.toml.sample /usr/share/usb-enforcer/config.toml.sample

# Install documentation
mkdir -p /usr/share/doc/usb-enforcer
cp -r "$PROJECT_ROOT/docs"/* /usr/share/doc/usb-enforcer/

# Convert markdown to HTML for better display
if command -v python3 >/dev/null 2>&1 && python3 -c "import markdown" 2>/dev/null; then
    echo "Converting documentation to HTML..."
    mkdir -p /usr/share/doc/usb-enforcer/html
    python3 "$PROJECT_ROOT/scripts/convert-docs-to-html.py" "$PROJECT_ROOT/docs" /usr/share/doc/usb-enforcer/html || echo "Warning: HTML conversion failed, markdown docs still available"
fi

echo
echo "===================================="
echo "Installation completed successfully!"
echo "===================================="
echo
echo "To launch the admin GUI:"
echo "  - From application menu: Search for 'USB Enforcer Admin'"
echo "  - From command line: sudo usb-enforcer-admin"
echo "  - Or use: pkexec usb-enforcer-admin"
echo
echo "The admin GUI will edit: /etc/usb-enforcer/config.toml"
echo
echo "Documentation is available at: /usr/share/doc/usb-enforcer/"
echo

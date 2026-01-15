#!/bin/bash
# Cleanup script to remove old USB enforcer daemon and ensure new one runs

set -e

echo "=== USB Enforcer Daemon Cleanup ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "This script must be run as root (use sudo)"
    exit 1
fi

echo "1. Stopping old usb-encryption-enforcer daemon..."
if systemctl is-active --quiet usb-encryption-enforcer 2>/dev/null; then
    systemctl stop usb-encryption-enforcer
    echo "   ✓ Stopped usb-encryption-enforcer service"
else
    echo "   - Service not running"
fi

# Kill any remaining old daemon processes
if pgrep -f "usb-encryption-enforcerd" > /dev/null; then
    echo "   - Killing remaining usb-encryption-enforcerd processes..."
    pkill -f "usb-encryption-enforcerd" || true
    sleep 1
fi

echo ""
echo "2. Disabling old usb-encryption-enforcer daemon..."
if systemctl is-enabled --quiet usb-encryption-enforcer 2>/dev/null; then
    systemctl disable usb-encryption-enforcer
    echo "   ✓ Disabled usb-encryption-enforcer service"
else
    echo "   - Service not enabled"
fi

echo ""
echo "3. Checking new usb-enforcer daemon..."
NEW_DAEMON_PID=$(pgrep -f "/usr/lib/usb-enforcer/.*/python.*usb_enforcer.daemon" || echo "")

if [ -n "$NEW_DAEMON_PID" ]; then
    echo "   ✓ New daemon running (PID: $NEW_DAEMON_PID)"
    
    # Check if it has content scanning initialized
    if journalctl _PID=$NEW_DAEMON_PID --since "1 hour ago" | grep -q "Content scanner initialized"; then
        echo "   ✓ Content scanning is initialized"
    else
        echo "   ⚠ Content scanning may not be initialized"
    fi
else
    echo "   ✗ New daemon not running!"
    echo "   Starting new daemon..."
    
    # Try to start via systemd
    if systemctl start usb-enforcer 2>/dev/null; then
        echo "   ✓ Started usb-enforcer service"
    else
        echo "   ⚠ Could not start via systemd, may need manual start"
    fi
fi

echo ""
echo "4. Current daemon status:"
echo "   Old daemons:"
if pgrep -f "usb-encryption-enforcerd" > /dev/null; then
    ps aux | grep "usb-encryption-enforcerd" | grep -v grep || echo "   None"
else
    echo "   ✓ None running"
fi

echo ""
echo "   New daemon:"
ps aux | grep "/usr/lib/usb-enforcer" | grep daemon | grep -v grep || echo "   ✗ Not running"

echo ""
echo "=== Cleanup Complete ==="
echo ""
echo "Next steps:"
echo "1. Unmount your encrypted USB device:"
echo "   $ udisksctl unmount -b /dev/mapper/My_Drive_1"
echo ""
echo "2. Lock (close) the LUKS container:"
echo "   $ udisksctl lock -b /dev/sda"
echo ""
echo "3. Reinsert or unlock the USB device again"
echo "   The new daemon should now intercept it and create the FUSE overlay"
echo ""
echo "4. Try copying the SSN test file again - it should be blocked!"
echo ""

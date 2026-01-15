#!/bin/bash
# Restart USB Enforcer with content scanning

echo "=== Restarting USB Enforcer System ==="

# 1. Stop everything
echo "1. Stopping services..."
sudo pkill -f "usb-enforcerd"
pkill -f "usb_enforcer_ui"
pkill -f "test-ui-signals"

# 2. Clean up mounts
echo "2. Cleaning up USB mounts..."
sudo umount -l /run/media/$USER/My* 2>/dev/null || true
sleep 1

# 3. Start daemon
echo "3. Starting daemon..."
sudo nohup /usr/libexec/usb-enforcerd --config /etc/usb-enforcer/config.toml > /tmp/usb-enforcer.log 2>&1 &
sleep 3

# 4. Verify daemon started
if sudo grep -q "USB encryption enforcer daemon starting" /tmp/usb-enforcer.log; then
    echo "   ✓ Daemon started successfully"
else
    echo "   ✗ Daemon failed to start"
    exit 1
fi

# 5. Start UI
echo "4. Starting UI..."
/usr/lib/usb-enforcer/.venv/bin/python3 -u /usr/lib/usb-enforcer/usb_enforcer_ui.py > ~/usb-ui.log 2>&1 &
sleep 2

echo ""
echo "=== System Ready ==="
echo ""
echo "Now:"
echo "  1. Insert and unlock your USB drive"
echo "  2. Wait for it to mount"
echo "  3. Try copying ~/test-ssn.txt to the USB"
echo "  4. You should see a notification when it's blocked"
echo ""
echo "Monitor logs:"
echo "  Daemon: tail -f /tmp/usb-enforcer.log"
echo "  UI: tail -f ~/usb-ui.log"
echo ""

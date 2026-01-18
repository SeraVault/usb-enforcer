# USB Enforcer Administration GUI - Quick Start

Get up and running with the USB Enforcer Administration GUI in 5 minutes.

## Installation

### Option 1: Install from Package (Recommended)

**Debian/Ubuntu:**
```bash
cd /path/to/usb-enforcer
make deb-admin
sudo dpkg -i dist/usb-enforcer-admin_*.deb
```

**Fedora/RHEL:**
```bash
cd /path/to/usb-enforcer
make rpm-admin
sudo dnf install dist/usb-enforcer-admin-*.noarch.rpm
```

### Option 2: Quick Install Script

```bash
cd /path/to/usb-enforcer
sudo make admin-install
```

## Launch

### From Application Menu
1. Press Super/Windows key
2. Type "USB Enforcer Admin"
3. Click the application

### From Terminal
```bash
pkexec usb-enforcer-admin
```

## First-Time Setup

1. **Review Basic Settings**
   - Navigate to "Basic" section in sidebar
   - Set minimum passphrase length (default: 12)
   - Enable/disable notifications
   - Configure group exemptions if needed

2. **Configure Content Scanning**
   - Go to "Content Scanning" section
   - Enable scanning for sensitive data
   - Select categories to scan (financial, personal, etc.)
   - Set file size limits

3. **Adjust Security Settings**
   - Visit "Security" section
   - Review mount options
   - Configure token TTL if needed

4. **Save Configuration**
   - Click "Save Configuration" button (top right)
   - Restart daemon to apply:
     ```bash
     sudo systemctl restart usb-enforcerd
     ```

## Common Tasks

### Enable Write Access with Scanning
1. Basic → Enable "Allow Write with Content Scanning"
2. Content Scanning → Enable "Enable Content Scanning"
3. Save configuration

### Add Group Exemption
1. Basic → Scroll to "Exempted Groups"
2. Enter group names (one per line)
3. Save configuration

### Change Filesystem Type
1. Encryption → Select "Filesystem Type"
2. Choose: exfat (cross-platform), ext4 (Linux), or ntfs
3. Save configuration

### Adjust Scan Performance
1. Content Scanning → Modify "Max File Size (MB)"
2. Content Scanning → Set "Max Concurrent Scans"
3. Advanced → Configure cache settings
4. Save configuration

## Getting Help

### In-App Documentation
- Click any 📖 documentation link for detailed info
- Links open relevant docs in your default application

### View All Documentation
- Click Help icon (?) in header bar
- Select documentation topic
- Opens in system viewer or web browser

## Troubleshooting

### Can't Launch GUI
```bash
# Check dependencies
dpkg -l | grep -E "gtk-4|libadwaita|python3-gi"  # Debian/Ubuntu
rpm -qa | grep -E "gtk4|libadwaita|python3-gobject"  # Fedora/RHEL

# Run directly for error messages
python3 -c "from usb_enforcer.ui.admin import main; main()"
```

### Can't Save Configuration
```bash
# Check permissions
ls -la /etc/usb-enforcer/

# Ensure running with privileges
pkexec usb-enforcer-admin
```

### Settings Not Taking Effect
```bash
# Restart daemon
sudo systemctl restart usb-enforcerd

# Check daemon status
sudo systemctl status usb-enforcerd
```

## Next Steps

- Read [ADMIN-GUI.md](ADMIN-GUI.md) for complete documentation
- Review [ADMINISTRATION.md](ADMINISTRATION.md) for daemon management
- See [CONTENT-SCANNING-INTEGRATION.md](CONTENT-SCANNING-INTEGRATION.md) for DLP setup
- Check [GROUP-EXEMPTIONS.md](GROUP-EXEMPTIONS.md) for exemption configuration

## Support

- GitHub Issues: https://github.com/seravault/usb-enforcer/issues
- Documentation: https://github.com/seravault/usb-enforcer/tree/main/docs

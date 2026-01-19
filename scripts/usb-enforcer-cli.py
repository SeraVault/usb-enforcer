#!/usr/bin/env python3
"""
USB Enforcer CLI - Command-line interface for USB Enforcer

This tool provides device management and content scanning operations:
- List, unlock, encrypt, and monitor USB devices
- Test and manage content scanning features
"""

import sys
import argparse
import logging
import getpass
import json
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# Import content verification modules (optional)
try:
    from usb_enforcer.content_verification import ContentScanner, PatternLibrary
    from usb_enforcer.content_verification.config import ContentScanningConfig
    CONTENT_SCANNING_AVAILABLE = True
except ImportError:
    CONTENT_SCANNING_AVAILABLE = False

# Import device management modules
try:
    import pydbus
    from gi.repository import GLib
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False
    
try:
    from usb_enforcer import secret_socket
    SECRET_SOCKET_AVAILABLE = True
except ImportError:
    SECRET_SOCKET_AVAILABLE = False


def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


# ============================================================================
# Content Scanning Commands
# ============================================================================

def cmd_scan_file(args):
    """Scan a file for sensitive content"""
    if not CONTENT_SCANNING_AVAILABLE:
        print("Error: Content scanning not available. Install dependencies:")
        print("  sudo apt install python3-fusepy  # Or check requirements.txt")
        return 1
    
    filepath = Path(args.file)
    
    if not filepath.exists():
        print(f"Error: File not found: {filepath}")
        return 1
    
    # Initialize scanner
    config = {}
    if args.config:
        import toml
        config_data = toml.load(args.config)
        config = config_data.get('content_scanning', {})
    
    scanner = ContentScanner(config)
    
    print(f"Scanning: {filepath}")
    print(f"File size: {filepath.stat().st_size} bytes")
    print()
    
    # Scan file
    result = scanner.scan_file(filepath)
    
    # Display results
    print(f"Result: {'BLOCKED' if result.blocked else 'ALLOWED'}")
    print(f"Action: {result.action.value}")
    print(f"Reason: {result.reason}")
    print(f"Scan duration: {result.scan_duration:.3f}s")
    print()
    
    if result.matches:
        print(f"Found {len(result.matches)} sensitive pattern(s):")
        for i, match in enumerate(result.matches, 1):
            print(f"  {i}. {match.pattern_name} ({match.pattern_category}) - {match.severity}")
            print(f"     Position: {match.position}")
            if args.verbose:
                print(f"     Context: {match.context}")
        print()
    
    # Display statistics
    if args.stats:
        stats = scanner.get_statistics()
        print("Scanner Statistics:")
        print(f"  Patterns loaded: {stats['patterns_loaded']}")
        print(f"  By category:")
        for category, count in stats['patterns_by_category'].items():
            print(f"    {category}: {count}")
        if 'cache' in stats:
            cache_stats = stats['cache']
            print(f"  Cache:")
            print(f"    Entries: {cache_stats['entries']}")
            print(f"    Size: {cache_stats['size_mb']:.2f} MB")
            print(f"    Hit rate: {cache_stats['hit_rate']:.1f}%")
    
    return 0 if not result.blocked else 1


def cmd_scan_text(args):
    """Scan text content for sensitive data"""
    if not CONTENT_SCANNING_AVAILABLE:
        print("Error: Content scanning not available. Install dependencies.")
        return 1
    
    text = args.text
    
    # Initialize scanner
    scanner = ContentScanner()
    
    print(f"Scanning text ({len(text)} characters)")
    print()
    
    # Scan content
    result = scanner.scan_content(text.encode('utf-8'), "stdin")
    
    # Display results
    print(f"Result: {'BLOCKED' if result.blocked else 'ALLOWED'}")
    print(f"Action: {result.action.value}")
    print(f"Reason: {result.reason}")
    print()
    
    if result.matches:
        print(f"Found {len(result.matches)} sensitive pattern(s):")
        for i, match in enumerate(result.matches, 1):
            print(f"  {i}. {match.pattern_name} ({match.pattern_category}) - {match.severity}")
            print(f"     Position: {match.position}")
            if args.verbose:
                print(f"     Context: {match.context}")
    
    return 0 if not result.blocked else 1


def cmd_list_patterns(args):
    """List all available detection patterns"""
    if not CONTENT_SCANNING_AVAILABLE:
        print("Error: Content scanning not available. Install dependencies.")
        return 1
    
    # Initialize pattern library
    enabled_categories = None
    if args.category:
        enabled_categories = [args.category]
    
    lib = PatternLibrary(enabled_categories=enabled_categories)
    patterns = lib.get_all_patterns()
    
    print(f"Loaded {len(patterns)} patterns")
    print()
    
    # Group by category
    by_category = {}
    for pattern in patterns:
        category = pattern.category.value
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(pattern)
    
    # Display
    for category, category_patterns in sorted(by_category.items()):
        print(f"{category.UPPER()} ({len(category_patterns)} patterns):")
        for pattern in sorted(category_patterns, key=lambda p: p.name):
            print(f"  {pattern.name:25} {pattern.severity.value:10} {pattern.description}")
        print()
    
    return 0


def cmd_test_pattern(args):
    """Test a specific pattern against text"""
    if not CONTENT_SCANNING_AVAILABLE:
        print("Error: Content scanning not available. Install dependencies.")
        return 1
    
    pattern_name = args.pattern
    text = args.text
    
    # Initialize pattern library
    lib = PatternLibrary()
    patterns = lib.get_all_patterns()
    
    # Find pattern
    target_pattern = None
    for pattern in patterns:
        if pattern.name == pattern_name:
            target_pattern = pattern
            break
    
    if not target_pattern:
        print(f"Error: Pattern '{pattern_name}' not found")
        print(f"Use 'usb-enforcer-cli patterns' to see available patterns")
        return 1
    
    print(f"Testing pattern: {target_pattern.name}")
    print(f"Category: {target_pattern.category.value}")
    print(f"Severity: {target_pattern.severity.value}")
    print(f"Description: {target_pattern.description}")
    print(f"Regex: {target_pattern.regex}")
    print()
    
    # Test pattern
    matches = target_pattern.compiled_regex.finditer(text)
    found_matches = list(matches)
    
    if found_matches:
        print(f"Found {len(found_matches)} match(es):")
        for i, match in enumerate(found_matches, 1):
            matched_text = match.group(0)
            print(f"  {i}. Position {match.start()}-{match.end()}: '{matched_text}'")
            
            # Apply validator if present
            if target_pattern.validator:
                is_valid = target_pattern.validator(matched_text)
                print(f"     Validation: {'PASS' if is_valid else 'FAIL'}")
    else:
        print("No matches found")
    
    return 0


def cmd_config_show(args):
    """Show current configuration"""
    if not CONTENT_SCANNING_AVAILABLE:
        print("Error: Content scanning not available. Install dependencies.")
        return 1
    
    if args.file:
        import toml
        config_data = toml.load(args.file)
        content_scanning = config_data.get('content_scanning', {})
        config = ContentScanningConfig.from_dict(content_scanning)
    else:
        config = ContentScanningConfig()
    
    print("Content Scanning Configuration")
    print("=" * 50)
    print(f"Enabled: {config.enabled}")
    print(f"Scan encrypted devices: {config.scan_encrypted_devices}")
    print(f"Max file size: {config.max_file_size_mb} MB")
    print(f"Max scan time: {config.max_scan_time_seconds}s")
    print(f"Block on error: {config.block_on_error}")
    print()
    
    print("Patterns:")
    print(f"  Enabled categories: {', '.join(config.patterns.enabled_categories)}")
    print(f"  Disabled patterns: {', '.join(config.patterns.disabled_patterns) if config.patterns.disabled_patterns else 'None'}")
    print(f"  Custom patterns: {len(config.patterns.custom_patterns)}")
    print()
    
    print("Archives:")
    print(f"  Scan archives: {config.archives.scan_archives}")
    print(f"  Max depth: {config.archives.max_depth}")
    print(f"  Max members: {config.archives.max_members}")
    print(f"  Block encrypted: {config.archives.block_encrypted_archives}")
    print()
    
    print("Documents:")
    print(f"  Scan documents: {config.documents.scan_documents}")
    print(f"  Supported formats: {', '.join(config.documents.supported_formats)}")
    print()
    
    print("Policy:")
    print(f"  Action: {config.policy.action}")
    print(f"  Notify user: {config.policy.notify_user}")
    print(f"  Allow override: {config.policy.allow_override}")
    
    return 0


# ============================================================================
# Device Management Commands
# ============================================================================

def check_dbus_available():
    """Check if DBus is available"""
    if not DBUS_AVAILABLE:
        print("Error: DBus support not available. Install python3-pydbus:")
        print("  sudo apt install python3-pydbus  # Debian/Ubuntu")
        print("  sudo dnf install python3-pydbus  # Fedora/RHEL")
        return False
    return True


def get_dbus_proxy():
    """Get USB Enforcer DBus proxy"""
    try:
        bus = pydbus.SystemBus()
        proxy = bus.get("org.seravault.UsbEnforcer", "/org/seravault/UsbEnforcer")
        return proxy
    except Exception as e:
        print(f"Error: Could not connect to USB Enforcer daemon: {e}")
        print("Make sure the daemon is running: sudo systemctl status usb-enforcerd")
        return None


def cmd_list_devices(args):
    """List USB devices"""
    if not check_dbus_available():
        return 1
    
    proxy = get_dbus_proxy()
    if not proxy:
        return 1
    
    try:
        devices = proxy.ListDevices()
        
        if not devices:
            print("No USB devices detected")
            return 0
        
        if args.json:
            print(json.dumps(devices, indent=2))
            return 0
        
        print(f"Found {len(devices)} USB device(s):\n")
        
        for i, device in enumerate(devices, 1):
            devnode = device.get('devnode', 'unknown')
            device_type = device.get('device_type', 'unknown')
            state = device.get('state', 'unknown')
            fs_type = device.get('fs_type', 'none')
            mount_point = device.get('mount_point', '')
            
            print(f"{i}. {devnode}")
            print(f"   Type: {device_type}")
            print(f"   State: {state}")
            print(f"   Filesystem: {fs_type}")
            if mount_point:
                print(f"   Mounted: {mount_point}")
            print()
        
        return 0
    except Exception as e:
        print(f"Error listing devices: {e}")
        return 1


def cmd_device_status(args):
    """Check device status"""
    if not check_dbus_available():
        return 1
    
    proxy = get_dbus_proxy()
    if not proxy:
        return 1
    
    try:
        status = proxy.GetDeviceStatus(args.device)
        
        if args.json:
            print(json.dumps(status, indent=2))
            return 0
        
        print(f"Device: {args.device}")
        print(f"Type: {status.get('device_type', 'unknown')}")
        print(f"State: {status.get('state', 'unknown')}")
        print(f"Filesystem: {status.get('fs_type', 'none')}")
        
        mount_point = status.get('mount_point')
        if mount_point:
            print(f"Mounted: {mount_point}")
        
        encrypted = status.get('encrypted', False)
        print(f"Encrypted: {encrypted}")
        
        if encrypted:
            encryption_type = status.get('encryption_type', 'unknown')
            print(f"Encryption type: {encryption_type}")
        
        return 0
    except Exception as e:
        print(f"Error getting device status: {e}")
        return 1


def cmd_unlock_device(args):
    """Unlock an encrypted device"""
    if not check_dbus_available():
        return 1
    
    if not SECRET_SOCKET_AVAILABLE:
        print("Error: Secret socket module not available")
        return 1
    
    proxy = get_dbus_proxy()
    if not proxy:
        return 1
    
    # Get passphrase from user
    if args.passphrase:
        passphrase = args.passphrase
    else:
        try:
            passphrase = getpass.getpass(f"Enter passphrase for {args.device}: ")
        except KeyboardInterrupt:
            print("\nCancelled")
            return 130
    
    if not passphrase:
        print("Error: Passphrase cannot be empty")
        return 1
    
    try:
        # Send passphrase via secret socket, get token
        print(f"Unlocking {args.device}...")
        token = secret_socket.send_secret("unlock", args.device, passphrase)
        
        # Call DBus method with token
        result = proxy.RequestUnlock(args.device, "", token)
        
        print(f"Success: {result}")
        return 0
    except Exception as e:
        print(f"Error unlocking device: {e}")
        return 1


def cmd_encrypt_device(args):
    """Encrypt a device"""
    if not check_dbus_available():
        return 1
    
    if not SECRET_SOCKET_AVAILABLE:
        print("Error: Secret socket module not available")
        return 1
    
    proxy = get_dbus_proxy()
    if not proxy:
        return 1
    
    # Get passphrase from user
    if args.passphrase:
        passphrase = args.passphrase
        confirm = passphrase
    else:
        try:
            while True:
                passphrase = getpass.getpass(f"Enter passphrase for {args.device} (min 12 chars): ")
                if len(passphrase) < 12:
                    print("Passphrase must be at least 12 characters")
                    continue
                confirm = getpass.getpass("Confirm passphrase: ")
                if passphrase != confirm:
                    print("Passphrases do not match")
                    continue
                break
        except KeyboardInterrupt:
            print("\nCancelled")
            return 130
    
    if not passphrase or len(passphrase) < 12:
        print("Error: Passphrase must be at least 12 characters")
        return 1
    
    # Confirm data destruction
    if not args.yes:
        print(f"\nWARNING: This will DESTROY all data on {args.device}")
        try:
            confirm_input = input("Type 'yes' to continue: ")
        except KeyboardInterrupt:
            print("\nCancelled")
            return 130
        
        if confirm_input.lower() != "yes":
            print("Cancelled")
            return 0
    
    try:
        # Send passphrase via secret socket, get token
        print(f"Encrypting {args.device}...")
        token = secret_socket.send_secret("encrypt", args.device, passphrase)
        
        # Call DBus method with token
        result = proxy.RequestEncrypt(args.device, "", token, args.filesystem, args.label)
        
        print(f"Success: {result}")
        return 0
    except Exception as e:
        print(f"Error encrypting device: {e}")
        return 1


def cmd_monitor_events(args):
    """Monitor USB device events"""
    if not check_dbus_available():
        return 1
    
    print("Monitoring USB device events (Ctrl+C to stop)...\n")
    
    def on_event(event):
        """Event handler"""
        event_type = event.get('USB_EE_EVENT', 'unknown')
        devnode = event.get('DEVNODE', 'unknown')
        action = event.get('ACTION', '')
        
        if args.json:
            print(json.dumps(event))
        else:
            timestamp = event.get('timestamp', '')
            print(f"[{timestamp}] {event_type}: {devnode}")
            if action:
                print(f"  Action: {action}")
            
            # Show additional details based on event type
            if event_type == 'device_blocked':
                reason = event.get('reason', '')
                print(f"  Reason: {reason}")
            elif event_type == 'device_mounted':
                mount_point = event.get('mount_point', '')
                print(f"  Mounted at: {mount_point}")
            elif event_type == 'unformatted_drive':
                preferred_encryption = event.get('preferred_encryption', '')
                preferred_fs = event.get('preferred_filesystem', '')
                print(f"  Suggested: {preferred_encryption} + {preferred_fs}")
            
            print()
    
    try:
        bus = pydbus.SystemBus()
        bus.subscribe(
            sender="org.seravault.UsbEnforcer",
            iface="org.seravault.UsbEnforcer",
            signal="DeviceEvent",
            signal_fired=on_event
        )
        
        loop = GLib.MainLoop()
        loop.run()
    except KeyboardInterrupt:
        print("\nStopped monitoring")
        return 0
    except Exception as e:
        print(f"Error monitoring events: {e}")
        return 1


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='USB Enforcer CLI - Device management and content scanning',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Device management
  usb-enforcer-cli list                      List USB devices
  usb-enforcer-cli status /dev/sdb1          Check device status
  usb-enforcer-cli unlock /dev/sdb1          Unlock encrypted device
  usb-enforcer-cli encrypt /dev/sdb1         Encrypt a device
  usb-enforcer-cli monitor                   Monitor device events
  
  # Content scanning
  usb-enforcer-cli scan file.pdf             Scan a file
  usb-enforcer-cli patterns                  List patterns
  usb-enforcer-cli config                    Show configuration
"""
    )
    
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose output')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # ========================================================================
    # Device Management Commands
    # ========================================================================
    
    # list command
    list_parser = subparsers.add_parser('list', help='List USB devices')
    list_parser.add_argument('-j', '--json', action='store_true',
                           help='Output in JSON format')
    list_parser.set_defaults(func=cmd_list_devices)
    
    # status command
    status_parser = subparsers.add_parser('status', help='Check device status')
    status_parser.add_argument('device', help='Device path (e.g., /dev/sdb1)')
    status_parser.add_argument('-j', '--json', action='store_true',
                             help='Output in JSON format')
    status_parser.set_defaults(func=cmd_device_status)
    
    # unlock command
    unlock_parser = subparsers.add_parser('unlock', help='Unlock encrypted device')
    unlock_parser.add_argument('device', help='Device path (e.g., /dev/sdb1)')
    unlock_parser.add_argument('-p', '--passphrase', help='Passphrase (not recommended, use interactive prompt)')
    unlock_parser.set_defaults(func=cmd_unlock_device)
    
    # encrypt command
    encrypt_parser = subparsers.add_parser('encrypt', help='Encrypt a device with LUKS2')
    encrypt_parser.add_argument('device', help='Device path (e.g., /dev/sdb1)')
    encrypt_parser.add_argument('-l', '--label', default='EncryptedUSB',
                              help='Volume label (default: EncryptedUSB)')
    encrypt_parser.add_argument('-f', '--filesystem', default='exfat',
                              choices=['exfat', 'ext4', 'vfat'],
                              help='Filesystem type (default: exfat)')
    encrypt_parser.add_argument('-p', '--passphrase', help='Passphrase (not recommended, use interactive prompt)')
    encrypt_parser.add_argument('-y', '--yes', action='store_true',
                              help='Skip confirmation prompt')
    encrypt_parser.set_defaults(func=cmd_encrypt_device)
    
    # monitor command
    monitor_parser = subparsers.add_parser('monitor', help='Monitor USB device events')
    monitor_parser.add_argument('-j', '--json', action='store_true',
                              help='Output events in JSON format')
    monitor_parser.set_defaults(func=cmd_monitor_events)
    
    # ========================================================================
    # Content Scanning Commands
    # ========================================================================
    
    # scan command
    scan_parser = subparsers.add_parser('scan', help='Scan a file for sensitive content')
    scan_parser.add_argument('file', help='File to scan')
    scan_parser.add_argument('-c', '--config', help='Configuration file')
    scan_parser.add_argument('-s', '--stats', action='store_true',
                           help='Show scanner statistics')
    scan_parser.set_defaults(func=cmd_scan_file)
    
    # scan-text command
    scan_text_parser = subparsers.add_parser('scan-text', help='Scan text for sensitive content')
    scan_text_parser.add_argument('text', help='Text to scan')
    scan_text_parser.set_defaults(func=cmd_scan_text)
    
    # patterns command
    patterns_parser = subparsers.add_parser('patterns', help='List available patterns')
    patterns_parser.add_argument('-c', '--category',
                               choices=['pii', 'financial', 'medical', 'corporate', 'custom'],
                               help='Filter by category')
    patterns_parser.set_defaults(func=cmd_list_patterns)
    
    # test-pattern command
    test_parser = subparsers.add_parser('test-pattern', help='Test a pattern against text')
    test_parser.add_argument('pattern', help='Pattern name to test')
    test_parser.add_argument('text', help='Text to test against')
    test_parser.set_defaults(func=cmd_test_pattern)
    
    # config command
    config_parser = subparsers.add_parser('config', help='Show configuration')
    config_parser.add_argument('-f', '--file', help='Configuration file to load')
    config_parser.set_defaults(func=cmd_config_show)
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Setup logging
    setup_logging(args.verbose)
    
    # Execute command
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 130
    except Exception as e:
        logging.error(f"Error: {e}", exc_info=args.verbose)
        return 1


if __name__ == '__main__':
    sys.exit(main())

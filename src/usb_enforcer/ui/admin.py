"""USB Enforcer Administration GUI - Config Editor

A comprehensive graphical interface for editing USB Enforcer configuration.
Provides an intuitive way to manage all config.toml settings with validation,
inline help, and links to documentation.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango  # type: ignore

# Try to import WebKit for HTML documentation display
try:
    gi.require_version("WebKit", "6.0")
    from gi.repository import WebKit  # type: ignore
    WEBKIT_AVAILABLE = True
except (ImportError, ValueError):
    WEBKIT_AVAILABLE = False

# Try to import i18n, but use simple fallback if not available
try:
    from usb_enforcer.i18n import setup_i18n, _
    setup_i18n()
except (ImportError, ModuleNotFoundError):
    # Fallback for standalone admin installation
    def _(message: str) -> str:
        """Simple fallback translation function (English only)."""
        return message

try:
    import toml
    TOML_BINARY_MODE = False  # toml library uses text mode
except ImportError:
    # Fall back to tomli/tomllib for Python 3.11+
    try:
        import tomllib as toml  # type: ignore
        TOML_BINARY_MODE = True  # tomllib uses binary mode
    except ImportError:
        import tomli as toml  # type: ignore
        TOML_BINARY_MODE = True  # tomli uses binary mode


DEFAULT_CONFIG_PATH = "/etc/usb-enforcer/config.toml"
DOCS_BASE_PATH = "/usr/share/doc/usb-enforcer"


class ConfigValidator:
    """Validates configuration values."""
    
    @staticmethod
    def validate_passphrase_length(value: int) -> tuple[bool, str]:
        if value < 8:
            return False, _("Minimum passphrase length should be at least 8 characters")
        if value > 128:
            return False, _("Maximum passphrase length should not exceed 128 characters")
        return True, ""
    
    @staticmethod
    def validate_ttl(value: int) -> tuple[bool, str]:
        if value < 60:
            return False, _("TTL should be at least 60 seconds")
        if value > 3600:
            return False, _("TTL should not exceed 3600 seconds (1 hour)")
        return True, ""
    
    @staticmethod
    def validate_max_tokens(value: int) -> tuple[bool, str]:
        if value < 16:
            return False, _("Max tokens should be at least 16")
        if value > 1024:
            return False, _("Max tokens should not exceed 1024")
        return True, ""
    
    @staticmethod
    def validate_file_size(value: int) -> tuple[bool, str]:
        if value < 0:
            return False, _("File size cannot be negative (use 0 for unlimited)")
        if value > 10240:
            return False, _("File size limit should not exceed 10240 MB (10 GB)")
        return True, ""
    
    @staticmethod
    def validate_timeout(value: int) -> tuple[bool, str]:
        if value < 5:
            return False, _("Timeout should be at least 5 seconds")
        if value > 300:
            return False, _("Timeout should not exceed 300 seconds")
        return True, ""


class HelpDialog(Gtk.Window):
    """A help dialog that displays documentation."""
    
    def __init__(self, parent: Gtk.Window, title: str, content: str):
        super().__init__()
        self.set_title(title)
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(600, 400)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        
        text_view = Gtk.TextView()
        text_view.set_editable(False)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        text_view.get_buffer().set_text(content)
        
        scrolled.set_child(text_view)
        box.append(scrolled)
        
        close_button = Gtk.Button(label=_("Close"))
        close_button.connect("clicked", lambda _: self.close())
        box.append(close_button)
        
        self.set_child(box)


class AdminWindow(Gtk.ApplicationWindow):
    """Main administration window for USB Enforcer configuration."""
    
    def __init__(self, app: Adw.Application, config_path: Optional[str] = None):
        super().__init__(application=app, title=_("USB Enforcer Administration"))
        self.set_default_size(900, 700)
        self.set_icon_name("usb-enforcer")
        
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.config: Dict[str, Any] = {}
        self.modified = False
        
        # Header bar with save button
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label=_("USB Enforcer Configuration")))
        
        self.save_button = Gtk.Button(label=_("Save Configuration"))
        self.save_button.add_css_class("suggested-action")
        self.save_button.connect("clicked", self.on_save_clicked)
        self.save_button.set_sensitive(False)
        header.pack_end(self.save_button)

        self.restart_button = Gtk.Button(label=_("Restart Daemon"))
        self.restart_button.set_tooltip_text(_("Restart usb-enforcerd to reload configuration"))
        self.restart_button.connect("clicked", self.on_restart_clicked)
        header.pack_end(self.restart_button)
        
        # Help menu button
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("help-browser-symbolic")
        menu_button.set_tooltip_text(_("Documentation"))
        
        # Create help menu
        help_menu = Gio.Menu()
        help_menu.append(_("Administration Guide"), "app.help-admin")
        help_menu.append(_("Content Scanning"), "app.help-scanning")
        help_menu.append(_("Anti-Evasion"), "app.help-evasion")
        help_menu.append(_("Group Exemptions"), "app.help-exemptions")
        help_menu.append(_("Architecture Overview"), "app.help-architecture")
        help_menu.append(_("Testing Guide"), "app.help-testing")
        
        menu_button.set_menu_model(help_menu)
        header.pack_start(menu_button)
        
        # Setup help actions
        self.setup_help_actions()
        
        self.set_titlebar(header)
        
        # Main content
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Info bar for messages
        self.info_bar = Gtk.InfoBar()
        self.info_bar.set_visible(False)
        self.info_label = Gtk.Label()
        self.info_bar.add_child(self.info_label)
        self.info_bar.connect("response", lambda bar, _: bar.set_visible(False))
        main_box.append(self.info_bar)
        
        # Scrolled window with settings
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.content_box.set_margin_top(12)
        self.content_box.set_margin_bottom(12)
        self.content_box.set_margin_start(12)
        self.content_box.set_margin_end(12)
        
        scrolled.set_child(self.content_box)
        main_box.append(scrolled)
        
        self.set_child(main_box)
        
        # Load config and build UI
        self.load_config()
        self.build_ui()
    
    def setup_help_actions(self):
        """Setup actions for help menu items."""
        help_docs = {
            "help-admin": "ADMINISTRATION.md",
            "help-scanning": "CONTENT-SCANNING-INTEGRATION.md",
            "help-evasion": "ANTI-EVASION.md",
            "help-exemptions": "GROUP-EXEMPTIONS.md",
            "help-architecture": "ARCHITECTURE-REORGANIZATION.md",
            "help-testing": "TESTING.md"
        }
        
        for action_name, doc_file in help_docs.items():
            action = Gio.SimpleAction.new(action_name, None)
            action.connect("activate", lambda a, p, df=doc_file: self.open_documentation(df))
            self.get_application().add_action(action)
    
    def load_config(self):
        """Load configuration from file."""
        try:
            if os.path.exists(self.config_path):
                # toml library needs text mode, tomllib/tomli need binary
                mode = 'rb' if TOML_BINARY_MODE else 'r'
                with open(self.config_path, mode) as f:
                    self.config = toml.load(f)
            else:
                # Load from sample if main config doesn't exist
                sample_path = "/usr/share/usb-enforcer/config.toml.sample"
                if os.path.exists(sample_path):
                    mode = 'rb' if TOML_BINARY_MODE else 'r'
                    with open(sample_path, mode) as f:
                        self.config = toml.load(f)
                else:
                    # Use defaults
                    self.config = self.get_default_config()
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Config load error: {e}")
            print(error_details)
            self.show_error(_("Error loading configuration: {}\nUsing default configuration.").format(e))
            self.config = self.get_default_config()
    
    def get_default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            "enforce_on_usb_only": True,
            "allow_luks1_readonly": True,
            "allow_luks2": True,
            "allow_veracrypt": True,
            "allow_plaintext_write_with_scanning": True,
            "notification_enabled": True,
            "min_passphrase_length": 12,
            "exempted_groups": [],
            "secret_token_ttl_seconds": 300,
            "secret_token_max": 128,
            "default_plain_mount_opts": ["nodev", "nosuid", "noexec", "ro"],
            "default_encrypted_mount_opts": ["nodev", "nosuid", "rw"],
            "require_noexec_on_plain": True,
            "encryption_target_mode": "whole_disk",
            "filesystem_type": "exfat",
            "default_encryption_type": "luks2",
            "kdf": {"type": "argon2id"},
            "cipher": {"type": "aes-xts-plain64", "key_size": 512},
            "content_scanning": {
                "enabled": True,
                "enforce_on_encrypted_devices": True,
                "action": "block",
                "enabled_categories": ["financial", "personal", "authentication", "medical"],
                "max_file_size_mb": 100,
                "oversize_action": "block",
                "scan_timeout_seconds": 30,
                "max_concurrent_scans": 2,
                "archive_scanning_enabled": True,
                "max_archive_depth": 5,
                "document_scanning_enabled": True,
                "ngram_analysis_enabled": True,
                "cache_enabled": True,
                "cache_max_size_mb": 100,
            }
        }
    
    def build_ui(self):
        """Build the UI with all configuration options."""
        # Create tabbed interface
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        
        stack_sidebar = Gtk.StackSidebar()
        stack_sidebar.set_stack(self.stack)
        
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_start_child(stack_sidebar)
        paned.set_end_child(self.stack)
        paned.set_position(200)
        
        # Clear content and add paned view
        while self.content_box.get_first_child():
            self.content_box.remove(self.content_box.get_first_child())
        self.content_box.append(paned)
        
        # Build each section
        self.build_status_section()
        self.build_basic_section()
        self.build_security_section()
        self.build_encryption_section()
        self.build_scanning_section()
        self.build_advanced_section()
    
    def build_status_section(self):
        """Build system status page."""
        page = self.create_page(_("System Status"))
        
        self.add_section_header(page, _("USB Enforcer System Status"), 
                               _("Monitor all components of USB Enforcer"))
        
        # Create status items container
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        status_box.set_margin_top(12)
        status_box.set_margin_bottom(12)
        status_box.set_margin_start(12)
        status_box.set_margin_end(12)
        
        # Check if main package is installed
        main_package_installed = self.check_main_package_installed()
        
        if not main_package_installed:
            # Show info banner about missing main package
            info_banner = Adw.Banner()
            info_banner.set_title(_("Main Package Not Installed"))
            info_banner.set_button_label(_("Learn More"))
            info_banner.connect("button-clicked", self.on_main_package_help)
            status_box.append(info_banner)
            
            info_label = Gtk.Label()
            info_label.set_markup(
                _("<b>Note:</b> This is the standalone admin GUI package. "
                  "To use USB Enforcer, install the main package:\n\n"
                  "<tt>sudo apt install usb-enforcer</tt>  (Debian/Ubuntu)\n"
                  "<tt>sudo dnf install usb-enforcer</tt>  (RHEL/Fedora)")
            )
            info_label.set_wrap(True)
            info_label.set_xalign(0)
            info_label.set_margin_top(12)
            info_label.set_margin_bottom(12)
            status_box.append(info_label)
        
        # System Service Status
        status_box.append(self.create_status_group(_("System Service"), [
            (_("Daemon Service"), self.check_systemd_service("usb-enforcerd.service")),
            (_("User UI Service"), self.check_systemd_user_service("usb-enforcer-ui.service")),
            (_("DBus Service"), self.check_dbus_service()),
        ]))
        
        # Configuration Status
        config_status = []
        config_file_check = self.check_config_file()
        config_status.append((_("Config File"), config_file_check))
        
        # If config doesn't exist but we can create a sample
        if config_file_check[0] == "error" and not main_package_installed:
            config_status.append((_("Sample Config"), self.check_file_exists("/usr/share/usb-enforcer/config.toml.sample")))
        
        if os.path.exists(self.config_path):
            try:
                mode = 'rb' if TOML_BINARY_MODE else 'r'
                with open(self.config_path, mode) as f:
                    config = toml.load(f)
                    # Check key settings
                    if config.get("enforce_on_usb_only"):
                        config_status.append((_("Enforcement Scope"), ("info", _("USB devices only"))))
                    else:
                        config_status.append((_("Enforcement Scope"), ("warning", _("All storage devices"))))
                    
                    if config.get("content_scanning", {}).get("enabled"):
                        config_status.append((_("Content Scanning"), ("success", _("Enabled"))))
                    else:
                        config_status.append((_("Content Scanning"), ("info", _("Disabled"))))
            except Exception as e:
                config_status.append((_("Config Parsing"), ("error", str(e))))
        
        status_box.append(self.create_status_group(_("Configuration"), config_status))
        
        # System Integration Status (from main package)
        integration_items = [
            (_("Udev Rules"), self.check_file_exists("/usr/lib/udev/rules.d/49-usb-enforcer.rules")),
            (_("Udisks2 Rules"), self.check_file_exists("/usr/lib/udev/rules.d/80-udisks2-usb-enforcer.rules")),
            (_("PolicyKit Rules"), self.check_file_exists("/etc/polkit-1/rules.d/49-usb-enforcer.rules")),
            (_("DBus Config"), self.check_file_exists("/etc/dbus-1/system.d/org.seravault.UsbEnforcer.conf")),
        ]
        
        group_title = _("System Integration") if main_package_installed else _("System Integration (from main package)")
        status_box.append(self.create_status_group(group_title, integration_items))
        
        # Refresh button
        refresh_button = Gtk.Button(label=_("Refresh Status"))
        refresh_button.set_margin_top(12)
        refresh_button.connect("clicked", lambda btn: self.refresh_status())
        status_box.append(refresh_button)
        
        page.append(status_box)
        
        self.stack.add_titled(page, "status", _("System Status"))
    
    def check_main_package_installed(self) -> bool:
        """Check if the main usb-enforcer package is installed."""
        # Check for daemon script which is only in main package
        daemon_path = "/usr/libexec/usb-enforcerd"
        if not os.path.exists(daemon_path):
            daemon_path = "/usr/lib/usb-enforcer/usb-enforcerd"
        return os.path.exists(daemon_path)
    
    def on_main_package_help(self, banner):
        """Show help about installing main package."""
        dialog = Adw.MessageDialog.new(self)
        dialog.set_heading(_("Main Package Required"))
        dialog.set_body(
            _("The usb-enforcer-admin package only contains the configuration GUI. "
              "To use USB Enforcer, you need to install the main package:\n\n"
              "Debian/Ubuntu:\n"
              "  sudo apt install usb-enforcer\n\n"
              "RHEL/Fedora:\n"
              "  sudo dnf install usb-enforcer\n\n"
              "The main package includes:\n"
              "• System daemon (usb-enforcerd)\n"
              "• Udev and PolicyKit rules\n"
              "• DBus service\n"
              "• User interface and wizard")
        )
        dialog.add_response("ok", _("OK"))
        dialog.set_default_response("ok")
        dialog.present()
    
    def check_systemd_service(self, service_name: str) -> tuple[str, str]:
        """Check if a systemd service is active."""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip() == "active":
                return ("success", _("Running"))
            else:
                return ("error", _("Not running"))
        except Exception as e:
            return ("error", _("Error checking: {}").format(str(e)))
    
    def check_systemd_user_service(self, service_name: str) -> tuple[str, str]:
        """Check if a systemd user service is active."""
        # When running as root (via pkexec), we need to check user services differently
        try:
            # First try direct check (works if running as user)
            result = subprocess.run(
                ["systemctl", "--user", "is-active", service_name],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip() == "active":
                return ("success", _("Running"))
            
            # If that failed, try checking for any logged-in user
            # Get list of logged-in users
            result = subprocess.run(
                ["loginctl", "list-users", "--no-legend"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        uid = line.split()[0]
                        # Check this user's service
                        check_result = subprocess.run(
                            ["systemctl", "--user", "--machine", f"{uid}@", "is-active", service_name],
                            capture_output=True, text=True, timeout=2
                        )
                        if check_result.returncode == 0 and check_result.stdout.strip() == "active":
                            return ("success", _("Running"))
            
            return ("info", _("Not running (optional)"))
        except Exception as e:
            return ("info", _("Unable to check"))
    
    def check_dbus_service(self) -> tuple[str, str]:
        """Check if the DBus service is available."""
        try:
            result = subprocess.run(
                ["busctl", "status", "org.seravault.UsbEnforcer"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                return ("success", _("Available"))
            else:
                return ("error", _("Not available"))
        except Exception as e:
            return ("error", _("Error checking: {}").format(str(e)))
    
    def check_config_file(self) -> tuple[str, str]:
        """Check configuration file status."""
        if os.path.exists(self.config_path):
            try:
                stat = os.stat(self.config_path)
                if stat.st_size == 0:
                    return ("warning", _("File is empty"))
                return ("success", _("Present ({} bytes)").format(stat.st_size))
            except Exception as e:
                return ("error", str(e))
        else:
            # Config doesn't exist - check if we can suggest creating from sample
            sample_path = "/usr/share/usb-enforcer/config.toml.sample"
            if os.path.exists(sample_path):
                return ("warning", _("Not found (sample available)"))
            return ("error", _("Not found"))
    
    def check_file_exists(self, path: str) -> tuple[str, str]:
        """Check if a file exists."""
        if os.path.exists(path):
            return ("success", _("Installed"))
        else:
            return ("error", _("Not installed"))
    
    def create_status_group(self, title: str, items: list) -> Gtk.Widget:
        """Create a status group with multiple status items."""
        group = Adw.PreferencesGroup()
        group.set_title(title)
        
        for label, (status_type, status_text) in items:
            row = Adw.ActionRow()
            row.set_title(label)
            
            status_box = Gtk.Box(spacing=6)
            
            # Status icon
            if status_type == "success":
                icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                icon.add_css_class("success")
            elif status_type == "error":
                icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
                icon.add_css_class("error")
            elif status_type == "warning":
                icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
                icon.add_css_class("warning")
            else:  # info
                icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic")
            
            status_box.append(icon)
            
            status_label = Gtk.Label(label=status_text)
            status_box.append(status_label)
            
            row.add_suffix(status_box)
            group.add(row)
        
        return group
    
    def refresh_status(self):
        """Refresh the status page."""
        # Rebuild the status section
        # Find and remove the old status page
        child = self.stack.get_child_by_name("status")
        if child:
            self.stack.remove(child)
        
        # Rebuild it
        self.build_status_section()
    
    def build_basic_section(self):
        """Build basic enforcement settings."""
        page = self.create_page(_("Basic Enforcement"))
        
        self.add_section_header(page, _("Basic Settings"), 
                               _("Core enforcement policies for USB devices"))
        
        self.add_switch(page, "enforce_on_usb_only", 
                       _("Only Enforce on USB Devices"),
                       _("When enabled, only USB devices are subject to enforcement. "
                       "Other storage devices (SATA, NVMe) are not affected."),
                       "ADMINISTRATION.md#enforcement-scope")
        
        # Add section for unencrypted drive policy
        self.add_section_header(page, _("Unencrypted Drive Policy"), 
                               _("Control access to USB drives without encryption"))
        
        # Helper to manage the inverse relationship
        require_encryption_value = not self.config.get("allow_plaintext_write_with_scanning", False)
        
        row = Adw.ActionRow()
        row.set_title(_("Require Encryption"))
        row.set_subtitle(_("Block write access to unencrypted USB drives. "
                          "Only encrypted drives (LUKS2/VeraCrypt) can be written to. "
                          "Unencrypted drives will be mounted read-only."))
        
        switch = Gtk.Switch()
        switch.set_valign(Gtk.Align.CENTER)
        switch.set_active(require_encryption_value)
        switch.connect("notify::active", self.on_require_encryption_toggled)
        row.add_suffix(switch)
        row.set_activatable_widget(switch)
        page.append(row)
        
        # Store reference for updates
        self.require_encryption_switch = switch
        
        self.add_section_header(page, _("Allowed Encryption Types"), 
                               _("Select which encryption formats are permitted"))
        
        self.add_switch(page, "allow_luks1_readonly", 
                       _("Allow LUKS1 (Read-Only)"),
                       _("Allow older LUKS1 encrypted devices in read-only mode. "
                       "LUKS2 is recommended for better security."),
                       "ADMINISTRATION.md#luks-versions")
        
        self.add_switch(page, "allow_luks2", 
                       _("Allow LUKS2"),
                       _("Allow LUKS2 encrypted devices to be unlocked. "
                       "LUKS2 is the modern Linux encryption standard."),
                       "ADMINISTRATION.md#luks-versions")
        
        self.add_switch(page, "allow_veracrypt", 
                       _("Allow VeraCrypt"),
                       _("Allow VeraCrypt encrypted devices to be unlocked. "
                       "VeraCrypt is cross-platform (Windows/Mac/Linux)."),
                       "ADMINISTRATION.md#veracrypt")
        
        self.add_section_header(page, _("Other Settings"), 
                               _("Additional enforcement options"))
        
        self.add_switch(page, "notification_enabled", 
                       _("Desktop Notifications"),
                       _("Show desktop notifications when USB devices are connected "
                       "or blocked."),
                       "NOTIFICATIONS.md")
        
        self.add_spin_button(page, "min_passphrase_length",
                           _("Minimum Passphrase Length"),
                           _("Minimum number of characters required for encryption passphrases. "
                           "Recommended: 12 or higher."),
                           8, 128, 1, ConfigValidator.validate_passphrase_length,
                           "ADMINISTRATION.md#passphrase-requirements")
        
        self.add_text_list(page, "exempted_groups",
                          _("Exempted Groups"),
                          _("Linux groups that are exempt from USB enforcement. "
                          "Users in these groups can use any USB devices without restrictions. "
                          "Enter one group name per line."),
                          "GROUP-EXEMPTIONS.md")
        
        self.stack.add_titled(page, "basic", _("Basic"))
    
    def build_security_section(self):
        """Build security settings."""
        page = self.create_page(_("Security Settings"))
        
        self.add_section_header(page, _("Access Control"), 
                               _("Secret token and socket security settings"))
        
        self.add_spin_button(page, "secret_token_ttl_seconds",
                           _("Token TTL (seconds)"),
                           _("Time-to-live for one-time tokens used in passphrase handoff. "
                           "After this time, tokens expire and cannot be used."),
                           60, 3600, 30, ConfigValidator.validate_ttl,
                           "ADMINISTRATION.md#secret-tokens")
        
        self.add_spin_button(page, "secret_token_max",
                           _("Maximum Outstanding Tokens"),
                           _("Maximum number of tokens kept in memory at once. "
                           "Prevents memory exhaustion from token spam."),
                           16, 1024, 16, ConfigValidator.validate_max_tokens,
                           "ADMINISTRATION.md#secret-tokens")
        
        self.add_section_header(page, _("Mount Options"), 
                               _("Security flags for mounting USB devices"))
        
        self.add_text_list(page, "default_plain_mount_opts",
                          _("Plaintext Mount Options"),
                          _("Mount options for unencrypted USB devices. "
                          "Recommended: nodev, nosuid, noexec, ro"),
                          "ADMINISTRATION.md#mount-security")
        
        self.add_text_list(page, "default_encrypted_mount_opts",
                          _("Encrypted Mount Options"),
                          _("Mount options for encrypted USB devices. "
                          "Recommended: nodev, nosuid, rw"),
                          "ADMINISTRATION.md#mount-security")
        
        self.add_switch(page, "require_noexec_on_plain", 
                       _("Require No-Execute on Plaintext"),
                       _("Prevent execution of binaries from unencrypted USB devices. "
                       "Recommended for security."),
                       "ADMINISTRATION.md#execution-protection")
        
        self.stack.add_titled(page, "security", _("Security"))
    
    def build_encryption_section(self):
        """Build encryption settings."""
        page = self.create_page(_("Encryption Settings"))
        
        self.add_section_header(page, _("Encryption Defaults"), 
                               _("Default settings for USB device encryption"))
        
        self.add_dropdown(page, "default_encryption_type",
                        _("Default Encryption Type"),
                        _("luks2: Linux Unified Key Setup (Linux only)\n"
                        "veracrypt: VeraCrypt (Cross-platform: Windows/Mac/Linux)\n"
                        "Note: VeraCrypt must be installed separately"),
                        ["luks2", "veracrypt"],
                        "ADMINISTRATION.md#encryption-type")
        
        self.add_dropdown(page, "encryption_target_mode",
                        _("Encryption Target"),
                        _("whole_disk: Encrypt entire disk\n"
                        "partition: Encrypt specific partition only"),
                        ["whole_disk", "partition"],
                        "ADMINISTRATION.md#encryption-modes")
        
        self.add_dropdown(page, "filesystem_type",
                        _("Filesystem Type"),
                        _("Filesystem to use after encryption:\n"
                        "exfat: Cross-platform (Windows/Mac/Linux)\n"
                        "ext4: Linux native, journaling\n"
                        "ntfs: Windows-focused"),
                        ["exfat", "ext4", "ntfs"],
                        "ADMINISTRATION.md#filesystem-types")
        
        self.add_section_header(page, _("Key Derivation"), 
                               _("KDF (Key Derivation Function) settings"))
        
        kdf_type = self.config.get("kdf", {}).get("type", "argon2id")
        self.add_dropdown(page, "kdf.type",
                        _("KDF Algorithm"),
                        _("argon2id: Recommended, resistant to GPU attacks\n"
                        "pbkdf2: Older, less secure"),
                        ["argon2id", "pbkdf2"],
                        "ADMINISTRATION.md#kdf")
        
        self.add_section_header(page, _("Cipher Settings"), 
                               _("Encryption algorithm configuration"))
        
        self.add_dropdown(page, "cipher.type",
                        _("Cipher Algorithm"),
                        _("aes-xts-plain64: Recommended for disk encryption\n"
                        "aes-cbc-essiv:sha256: Older algorithm"),
                        ["aes-xts-plain64", "aes-cbc-essiv:sha256"],
                        "ADMINISTRATION.md#cipher")
        
        self.add_dropdown(page, "cipher.key_size",
                        _("Key Size (bits)"),
                        _("512: Maximum security (recommended)\n"
                        "256: Standard security"),
                        [256, 512],
                        "ADMINISTRATION.md#key-size")
        
        self.stack.add_titled(page, "encryption", _("Encryption"))
    
    def build_scanning_section(self):
        """Build content scanning settings."""
        page = self.create_page(_("Content Scanning"))
        
        self.add_section_header(page, _("Content Scanning (DLP)"), 
                               _("Data Loss Prevention through real-time content scanning"))
        
        cs = self.config.get("content_scanning", {})
        
        self.add_switch(page, "content_scanning.enabled", 
                       _("Enable Content Scanning"),
                       _("Enable real-time scanning of files for sensitive data. "
                       "Prevents writing credit cards, SSNs, API keys, etc. to USB devices."),
                       "CONTENT-SCANNING-INTEGRATION.md")
        
        self.add_switch(page, "content_scanning.enforce_on_encrypted_devices", 
                       _("Scan Encrypted Devices"),
                       _("When enabled, scanning applies to both encrypted and unencrypted devices. "
                       "When disabled, scanning only applies to unencrypted devices."),
                       "CONTENT-SCANNING-INTEGRATION.md#enforcement-scope")
        
        self.add_dropdown(page, "content_scanning.action",
                        _("Action on Detection"),
                        _("block: Prevent writing files with sensitive data\n"
                        "warn: Allow write but show warning\n"
                        "log_only: Allow write and log to journal"),
                        ["block", "warn", "log_only"],
                        "CONTENT-SCANNING-INTEGRATION.md#actions")
        
        self.add_section_header(page, _("Scan Categories"), 
                               _("Types of sensitive data to detect"))
        
        categories = cs.get("enabled_categories", [])
        self.add_checkboxes(page, "content_scanning.enabled_categories",
                          _("Enabled Categories"),
                          [
                              ("financial", _("Financial (credit cards, bank accounts, SWIFT, IBAN)")),
                              ("personal", _("Personal (SSN, passport, driver license, phone)")),
                              ("authentication", _("Authentication (API keys, passwords, tokens)")),
                              ("medical", _("Medical (medical records, insurance IDs)"))
                          ],
                          categories,
                          "FILE-TYPE-SUPPORT.md#data-categories")
        
        self.add_section_header(page, _("Performance Settings"), 
                               _("Scanning performance and limits"))
        
        self.add_spin_button(page, "content_scanning.max_file_size_mb",
                           _("Max File Size (MB)"),
                           _("Maximum file size to scan (0 = unlimited). "
                           "Larger files may be skipped or sampled based on oversize_action."),
                           0, 10240, 10, ConfigValidator.validate_file_size,
                           "CONTENT-SCANNING-INTEGRATION.md#file-size-limits")
        
        self.add_dropdown(page, "content_scanning.oversize_action",
                        _("Oversize File Action"),
                        _("block: Block files exceeding max size\n"
                        "allow_unscanned: Allow without scanning"),
                        ["block", "allow_unscanned"],
                        "CONTENT-SCANNING-INTEGRATION.md#oversize-handling")
        
        self.add_spin_button(page, "content_scanning.scan_timeout_seconds",
                           _("Scan Timeout (seconds)"),
                           _("Maximum time to spend scanning a single file."),
                           5, 300, 5, ConfigValidator.validate_timeout,
                           "CONTENT-SCANNING-INTEGRATION.md#timeouts")
        
        self.add_spin_button(page, "content_scanning.max_concurrent_scans",
                           _("Max Concurrent Scans"),
                           _("Number of parallel scanning threads."),
                           1, 16, 1, None,
                           "CONTENT-SCANNING-INTEGRATION.md#concurrency")
        
        self.stack.add_titled(page, "scanning", _("Content Scanning"))
    
    def build_advanced_section(self):
        """Build advanced scanning settings."""
        page = self.create_page(_("Advanced Scanning"))
        
        cs = self.config.get("content_scanning", {})
        
        self.add_section_header(page, _("Archive Scanning"), 
                               _("Scanning files inside archives (ZIP, TAR, 7Z, RAR)"))
        
        self.add_switch(page, "content_scanning.archive_scanning_enabled", 
                       _("Scan Archive Contents"),
                       _("Extract and scan files inside archive files. "
                       "Prevents hiding sensitive data in compressed files."),
                       "FILE-TYPE-SUPPORT.md#archives")
        
        self.add_spin_button(page, "content_scanning.max_archive_depth",
                           _("Max Archive Depth"),
                           _("Maximum nesting level for archives (e.g., ZIP inside ZIP). "
                           "Prevents zip bomb attacks."),
                           1, 10, 1, None,
                           "FILE-TYPE-SUPPORT.md#archive-depth")
        
        self.add_section_header(page, _("Document Scanning"), 
                               _("Scanning Office and PDF documents"))
        
        self.add_switch(page, "content_scanning.document_scanning_enabled", 
                       _("Scan Documents"),
                       _("Extract and scan text from PDF, DOCX, XLSX, PPTX, ODT files."),
                       "FILE-TYPE-SUPPORT.md#documents")
        
        self.add_section_header(page, _("Machine Learning"), 
                               _("Advanced pattern detection"))
        
        self.add_switch(page, "content_scanning.ngram_analysis_enabled", 
                       _("N-gram Analysis"),
                       _("Use machine learning for pattern detection in unstructured text. "
                       "Helps detect obfuscated or formatted sensitive data."),
                       "CONTENT-SCANNING-INTEGRATION.md#ml")
        
        self.add_section_header(page, _("Caching"), 
                               _("Scan result caching for performance"))
        
        self.add_switch(page, "content_scanning.cache_enabled", 
                       _("Enable Scan Cache"),
                       _("Cache scan results based on file hash. "
                       "Improves performance for repeated scans of same files."),
                       "CONTENT-SCANNING-INTEGRATION.md#caching")
        
        self.add_spin_button(page, "content_scanning.cache_max_size_mb",
                           _("Cache Size (MB)"),
                           _("Maximum size of scan result cache."),
                           10, 1024, 10, ConfigValidator.validate_file_size,
                           "CONTENT-SCANNING-INTEGRATION.md#cache-size")
        
        self.add_section_header(page, _("Custom Patterns"), 
                               _("Define enterprise-specific sensitive data patterns"))
        
        # Add button to manage custom patterns
        custom_btn = Gtk.Button(label=_("Manage Custom Patterns"))
        custom_btn.connect("clicked", self.on_manage_custom_patterns)
        page.append(custom_btn)
        
        # Show count of current patterns
        patterns = self.config.get("content_scanning", {}).get("custom_patterns", [])
        count_label = Gtk.Label(
            label=_("{} custom pattern(s) defined").format(len(patterns)),
            xalign=0
        )
        count_label.add_css_class("dim-label")
        page.append(count_label)
        
        self.stack.add_titled(page, "advanced", _("Advanced"))
    
    def create_page(self, title: str) -> Gtk.Box:
        """Create a new settings page."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_top(12)
        page.set_margin_bottom(12)
        page.set_margin_start(12)
        page.set_margin_end(12)
        return page
    
    def add_section_header(self, page: Gtk.Box, title: str, description: str):
        """Add a section header with title and description."""
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        header_box.set_margin_top(12)
        
        title_label = Gtk.Label(label=title, xalign=0)
        title_label.add_css_class("title-2")
        header_box.append(title_label)
        
        desc_label = Gtk.Label(label=description, xalign=0, wrap=True)
        desc_label.add_css_class("dim-label")
        header_box.append(desc_label)
        
        separator = Gtk.Separator()
        header_box.append(separator)
        
        page.append(header_box)
    
    def add_switch(self, page: Gtk.Box, key: str, label: str, 
                   description: str, doc_link: Optional[str] = None):
        """Add a boolean switch control."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_margin_top(6)
        row.set_margin_bottom(6)
        
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        left_box.set_hexpand(True)
        
        # Label with help icon
        label_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        label_widget = Gtk.Label(label=label, xalign=0)
        label_row.append(label_widget)
        
        # Add help button if help text available
        if doc_link:
            help_text = self.get_help_text(key)
            if help_text:
                help_button = Gtk.Button()
                help_button.set_icon_name("help-about-symbolic")
                help_button.add_css_class("flat")
                help_button.add_css_class("circular")
                help_button.set_valign(Gtk.Align.CENTER)
                help_button.connect("clicked", lambda w: self.show_help_popover(w, help_text))
                label_row.append(help_button)
        
        left_box.append(label_row)
        
        desc_label = Gtk.Label(label=description, xalign=0, wrap=True)
        desc_label.add_css_class("dim-label")
        desc_label.add_css_class("caption")
        left_box.append(desc_label)
        
        row.append(left_box)
        
        switch = Gtk.Switch()
        switch.set_valign(Gtk.Align.CENTER)
        value = self.get_config_value(key, False)
        switch.set_active(bool(value))
        switch.connect("state-set", lambda w, state: self.on_value_changed(key, state))
        row.append(switch)
        
        page.append(row)
    
    def add_spin_button(self, page: Gtk.Box, key: str, label: str, 
                       description: str, min_val: int, max_val: int, step: int,
                       validator=None, doc_link: Optional[str] = None):
        """Add a spin button control for integer values."""
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        row.set_margin_top(6)
        row.set_margin_bottom(6)
        
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        left_box.set_hexpand(True)
        
        # Label with help icon
        label_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        label_widget = Gtk.Label(label=label, xalign=0)
        label_row.append(label_widget)
        
        # Add help button if help text available
        if doc_link:
            help_text = self.get_help_text(key)
            if help_text:
                help_button = Gtk.Button()
                help_button.set_icon_name("help-about-symbolic")
                help_button.add_css_class("flat")
                help_button.add_css_class("circular")
                help_button.set_valign(Gtk.Align.CENTER)
                help_button.connect("clicked", lambda w: self.show_help_popover(w, help_text))
                label_row.append(help_button)
        
        left_box.append(label_row)
        
        desc_label = Gtk.Label(label=description, xalign=0, wrap=True)
        desc_label.add_css_class("dim-label")
        desc_label.add_css_class("caption")
        left_box.append(desc_label)
        
        header_box.append(left_box)
        
        adjustment = Gtk.Adjustment(value=0, lower=min_val, upper=max_val, 
                                   step_increment=step, page_increment=step * 10)
        spin = Gtk.SpinButton(adjustment=adjustment)
        spin.set_valign(Gtk.Align.CENTER)
        value = self.get_config_value(key, min_val)
        spin.set_value(int(value))
        
        def on_spin_changed(widget):
            val = int(widget.get_value())
            if validator:
                valid, msg = validator(val)
                if not valid:
                    self.show_warning(msg)
                    return
            self.on_value_changed(key, val)
        
        spin.connect("value-changed", on_spin_changed)
        header_box.append(spin)
        
        row.append(header_box)
        page.append(row)
    
    def add_dropdown(self, page: Gtk.Box, key: str, label: str, 
                    description: str, options: list, doc_link: Optional[str] = None):
        """Add a dropdown control."""
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        row.set_margin_top(6)
        row.set_margin_bottom(6)
        
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        left_box.set_hexpand(True)
        
        # Label with help icon
        label_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        label_widget = Gtk.Label(label=label, xalign=0)
        label_row.append(label_widget)
        
        # Add help button if help text available
        if doc_link:
            help_text = self.get_help_text(key)
            if help_text:
                help_button = Gtk.Button()
                help_button.set_icon_name("help-about-symbolic")
                help_button.add_css_class("flat")
                help_button.add_css_class("circular")
                help_button.set_valign(Gtk.Align.CENTER)
                help_button.connect("clicked", lambda w: self.show_help_popover(w, help_text))
                label_row.append(help_button)
        
        left_box.append(label_row)
        
        desc_label = Gtk.Label(label=description, xalign=0, wrap=True)
        desc_label.add_css_class("dim-label")
        desc_label.add_css_class("caption")
        left_box.append(desc_label)
        
        header_box.append(left_box)
        
        # Create dropdown
        store = Gio.ListStore.new(Gtk.StringObject)
        for opt in options:
            store.append(Gtk.StringObject.new(str(opt)))
        
        dropdown = Gtk.DropDown(model=store)
        dropdown.set_valign(Gtk.Align.CENTER)
        
        current_value = self.get_config_value(key, options[0])
        try:
            # Handle both string and int comparisons
            if isinstance(current_value, int):
                idx = options.index(current_value)
            else:
                # Try to find as-is first
                try:
                    idx = options.index(current_value)
                except ValueError:
                    # Try converting to int if all options are ints
                    if all(isinstance(opt, int) for opt in options):
                        idx = options.index(int(current_value))
                    else:
                        idx = options.index(str(current_value))
            dropdown.set_selected(idx)
        except (ValueError, TypeError):
            dropdown.set_selected(0)
        
        def on_dropdown_changed(widget, _):
            selected = widget.get_selected()
            if selected < len(options):
                self.on_value_changed(key, options[selected])
        
        dropdown.connect("notify::selected", on_dropdown_changed)
        header_box.append(dropdown)
        
        row.append(header_box)
        page.append(row)
    
    def add_text_list(self, page: Gtk.Box, key: str, label: str, 
                     description: str, doc_link: Optional[str] = None):
        """Add a text view for list values (one per line)."""
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        row.set_margin_top(6)
        row.set_margin_bottom(6)
        
        # Label with help icon
        label_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        label_widget = Gtk.Label(label=label, xalign=0)
        label_row.append(label_widget)
        
        # Add help button if help text available
        if doc_link:
            help_text = self.get_help_text(key)
            if help_text:
                help_button = Gtk.Button()
                help_button.set_icon_name("help-about-symbolic")
                help_button.add_css_class("flat")
                help_button.add_css_class("circular")
                help_button.set_valign(Gtk.Align.CENTER)
                help_button.connect("clicked", lambda w: self.show_help_popover(w, help_text))
                label_row.append(help_button)
        
        row.append(label_row)
        
        desc_label = Gtk.Label(label=description, xalign=0, wrap=True)
        desc_label.add_css_class("dim-label")
        desc_label.add_css_class("caption")
        row.append(desc_label)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_min_content_height(100)
        scrolled.set_max_content_height(150)
        
        text_view = Gtk.TextView()
        text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        text_view.set_monospace(True)
        
        value = self.get_config_value(key, [])
        if isinstance(value, list):
            # Convert all items to strings to avoid type errors
            text_view.get_buffer().set_text("\n".join(str(v) for v in value))
        else:
            text_view.get_buffer().set_text(str(value))
        
        def on_text_changed(buffer):
            start = buffer.get_start_iter()
            end = buffer.get_end_iter()
            text = buffer.get_text(start, end, False)
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            self.on_value_changed(key, lines)
        
        text_view.get_buffer().connect("changed", on_text_changed)
        
        scrolled.set_child(text_view)
        row.append(scrolled)
        
        page.append(row)
    
    def add_checkboxes(self, page: Gtk.Box, key: str, label: str, 
                      options: list, current_values: list, 
                      doc_link: Optional[str] = None):
        """Add a group of checkboxes for multi-select."""
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        row.set_margin_top(6)
        row.set_margin_bottom(6)
        
        # Label with help icon
        label_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        label_widget = Gtk.Label(label=label, xalign=0)
        label_row.append(label_widget)
        
        # Add help button if help text available
        if doc_link:
            help_text = self.get_help_text(key)
            if help_text:
                help_button = Gtk.Button()
                help_button.set_icon_name("help-about-symbolic")
                help_button.add_css_class("flat")
                help_button.add_css_class("circular")
                help_button.set_valign(Gtk.Align.CENTER)
                help_button.connect("clicked", lambda w: self.show_help_popover(w, help_text))
                label_row.append(help_button)
        
        row.append(label_row)
        
        checkboxes = {}
        for opt_key, opt_label in options:
            check = Gtk.CheckButton(label=opt_label)
            check.set_active(opt_key in current_values)
            check.connect("toggled", lambda w, k=opt_key: self.on_checkbox_toggled(key, k, w.get_active(), checkboxes))
            checkboxes[opt_key] = check
            row.append(check)
        
        page.append(row)
    
    def on_checkbox_toggled(self, key: str, option: str, active: bool, all_checkboxes: dict):
        """Handle checkbox toggle."""
        selected = [k for k, cb in all_checkboxes.items() if cb.get_active()]
        self.on_value_changed(key, selected)
    
    def get_config_value(self, key: str, default: Any) -> Any:
        """Get a config value by key (supports nested keys like 'content_scanning.enabled')."""
        parts = key.split(".")
        value = self.config
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value
    
    def set_config_value(self, key: str, value: Any):
        """Set a config value by key (supports nested keys)."""
        parts = key.split(".")
        config = self.config
        
        # Navigate to the parent dict
        for part in parts[:-1]:
            if part not in config:
                config[part] = {}
            config = config[part]
        
        # Set the value
        config[parts[-1]] = value
    
    def on_value_changed(self, key: str, value: Any):
        """Handle any value change."""
        self.set_config_value(key, value)
        self.modified = True
        self.save_button.set_sensitive(True)
    
    def on_require_encryption_toggled(self, switch, _):
        """Handle require encryption toggle."""
        require_encryption = switch.get_active()
        # Inverse logic: if require encryption is ON, plaintext write must be OFF
        self.config["allow_plaintext_write_with_scanning"] = not require_encryption
        self.modified = True
        self.save_button.set_sensitive(True)
    
    def on_save_clicked(self, button):
        """Save configuration to file."""
        try:
            # Create backup
            if os.path.exists(self.config_path):
                backup_path = f"{self.config_path}.backup"
                shutil.copy2(self.config_path, backup_path)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            
            # Write config - handle both toml libraries
            with open(self.config_path, 'w') as f:
                if hasattr(toml, 'dump'):
                    toml.dump(self.config, f)
                else:
                    # For tomllib (read-only), fall back to manual TOML writing
                    import json
                    # Simple TOML writer for basic config
                    self.write_toml_manual(f, self.config)
            
            self.show_success(_("Configuration saved to {}").format(self.config_path))
            self.modified = False
            self.save_button.set_sensitive(False)
            
            # Suggest restarting daemon
            self.show_info(_("Configuration saved. Restart usb-enforcerd to apply changes."))
            
        except Exception as e:
            self.show_error(_("Failed to save configuration: {}").format(e))

    def on_restart_clicked(self, button):
        """Restart the daemon to apply configuration changes."""
        try:
            result = subprocess.run(
                ["systemctl", "restart", "usb-enforcerd"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.show_success(_("usb-enforcerd restarted."))
        except FileNotFoundError:
            self.show_error(_("systemctl not found; cannot restart service."))
        except subprocess.CalledProcessError as e:
            detail = e.stderr.strip() if e.stderr else str(e)
            self.show_error(_("Failed to restart usb-enforcerd: {}").format(detail))
    
    def on_manage_custom_patterns(self, button):
        """Open dialog to manage custom content scanning patterns."""
        dialog = Adw.Window()
        dialog.set_title(_("Custom Content Patterns"))
        dialog.set_default_size(700, 500)
        dialog.set_transient_for(self)
        dialog.set_modal(True)
        
        toolbar_view = Adw.ToolbarView()
        
        # Header
        header = Adw.HeaderBar()
        add_btn = Gtk.Button(label=_("Add Pattern"))
        add_btn.add_css_class("suggested-action")
        add_btn.connect("clicked", lambda w: self.add_custom_pattern_row(list_box))
        header.pack_start(add_btn)
        toolbar_view.add_top_bar(header)
        
        # Scrolled area with patterns
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        
        list_box = Gtk.ListBox()
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        list_box.add_css_class("boxed-list")
        
        # Load existing patterns
        patterns = self.config.get("content_scanning", {}).get("custom_patterns", [])
        for pattern in patterns:
            self.add_custom_pattern_row(list_box, pattern)
        
        scrolled.set_child(list_box)
        toolbar_view.set_content(scrolled)
        dialog.set_content(toolbar_view)
        
        # Save patterns when dialog closes
        dialog.connect("close-request", lambda d: self.save_custom_patterns(list_box))
        
        dialog.present()
    
    def add_custom_pattern_row(self, list_box: Gtk.ListBox, pattern: dict = None):
        """Add a row for editing a custom pattern."""
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        
        # Name field
        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        name_label = Gtk.Label(label=_("Name:"), xalign=0)
        name_label.set_size_request(120, -1)
        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text(_("e.g., employee_id"))
        if pattern:
            name_entry.set_text(pattern.get("name", ""))
        name_entry.set_hexpand(True)
        name_box.append(name_label)
        name_box.append(name_entry)
        box.append(name_box)
        
        # Description field
        desc_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        desc_label = Gtk.Label(label=_("Description:"), xalign=0)
        desc_label.set_size_request(120, -1)
        desc_entry = Gtk.Entry()
        desc_entry.set_placeholder_text(_("e.g., Company employee ID"))
        if pattern:
            desc_entry.set_text(pattern.get("description", ""))
        desc_entry.set_hexpand(True)
        desc_box.append(desc_label)
        desc_box.append(desc_entry)
        box.append(desc_box)
        
        # Category dropdown
        cat_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        cat_label = Gtk.Label(label=_("Category:"), xalign=0)
        cat_label.set_size_request(120, -1)
        
        categories = ["financial", "personal", "authentication", "medical"]
        store = Gio.ListStore.new(Gtk.StringObject)
        for cat in categories:
            store.append(Gtk.StringObject.new(cat))
        cat_dropdown = Gtk.DropDown(model=store)
        if pattern and pattern.get("category") in categories:
            cat_dropdown.set_selected(categories.index(pattern.get("category")))
        cat_box.append(cat_label)
        cat_box.append(cat_dropdown)
        box.append(cat_box)
        
        # Regex pattern field with validation
        regex_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        regex_label = Gtk.Label(label=_("Regex:"), xalign=0, valign=Gtk.Align.START)
        regex_label.set_size_request(120, -1)
        regex_entry = Gtk.Entry()
        regex_entry.set_placeholder_text(_("e.g., EMP-\\\\d{6}"))
        if pattern:
            regex_entry.set_text(pattern.get("regex", ""))
        regex_entry.set_hexpand(True)
        regex_box.append(regex_label)
        regex_box.append(regex_entry)
        box.append(regex_box)
        
        # Validation status
        validation_label = Gtk.Label(xalign=0)
        validation_label.add_css_class("caption")
        validation_label.set_margin_start(120 + 6)
        box.append(validation_label)
        
        # Pattern templates button
        templates_btn = Gtk.Button(label=_("Common Patterns ▾"))
        templates_btn.set_margin_start(120 + 6)
        templates_btn.connect("clicked", lambda w: self.show_pattern_templates(regex_entry))
        box.append(templates_btn)
        
        # Test area
        test_frame = Gtk.Frame()
        test_frame.set_margin_start(120 + 6)
        test_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        test_box.set_margin_top(6)
        test_box.set_margin_bottom(6)
        test_box.set_margin_start(6)
        test_box.set_margin_end(6)
        
        test_label = Gtk.Label(label=_("Test Pattern:"), xalign=0)
        test_label.add_css_class("heading")
        test_box.append(test_label)
        
        test_entry = Gtk.Entry()
        test_entry.set_placeholder_text(_("Enter sample text to test the pattern..."))
        test_box.append(test_entry)
        
        test_result = Gtk.Label(xalign=0, wrap=True)
        test_result.add_css_class("caption")
        test_box.append(test_result)
        
        test_btn = Gtk.Button(label=_("Test Pattern"))
        test_btn.connect("clicked", lambda w: self.test_regex_pattern(
            regex_entry.get_text(), test_entry.get_text(), test_result, validation_label))
        test_box.append(test_btn)
        
        test_frame.set_child(test_box)
        box.append(test_frame)
        
        # Validate regex on change
        regex_entry.connect("changed", lambda w: self.validate_regex(w.get_text(), validation_label))
        
        # Initial validation if pattern exists
        if pattern and pattern.get("regex"):
            self.validate_regex(pattern.get("regex"), validation_label)
        
        # Delete button
        delete_btn = Gtk.Button(label=_("Delete Pattern"))
        delete_btn.add_css_class("destructive-action")
        delete_btn.connect("clicked", lambda w: list_box.remove(row))
        box.append(delete_btn)
        
        # Store widget references for later retrieval
        row.name_entry = name_entry
        row.desc_entry = desc_entry
        row.cat_dropdown = cat_dropdown
        row.regex_entry = regex_entry
        
        row.set_child(box)
        list_box.append(row)
    
    def save_custom_patterns(self, list_box: Gtk.ListBox):
        """Save custom patterns from the dialog back to config."""
        patterns = []
        categories = ["financial", "personal", "authentication", "medical"]
        
        row = list_box.get_first_child()
        while row:
            if hasattr(row, 'name_entry'):
                name = row.name_entry.get_text().strip()
                desc = row.desc_entry.get_text().strip()
                regex = row.regex_entry.get_text().strip()
                cat_idx = row.cat_dropdown.get_selected()
                category = categories[cat_idx] if cat_idx < len(categories) else "personal"
                
                if name and regex:  # Only save if name and regex are provided
                    patterns.append({
                        "name": name,
                        "description": desc,
                        "category": category,
                        "regex": regex
                    })
            row = row.get_next_sibling()
        
        # Update config
        if "content_scanning" not in self.config:
            self.config["content_scanning"] = {}
        self.config["content_scanning"]["custom_patterns"] = patterns
        self.on_value_changed("content_scanning.custom_patterns", patterns)
    
    def validate_regex(self, pattern: str, label: Gtk.Label):
        """Validate a regex pattern and show result."""
        import re
        
        if not pattern:
            label.set_text("")
            return False
        
        try:
            re.compile(pattern)
            label.set_markup(_("<span foreground='green'>✓ Valid regex pattern</span>"))
            return True
        except re.error as e:
            label.set_markup(_("<span foreground='red'>✗ Invalid: {}</span>").format(e))
            return False
    
    def test_regex_pattern(self, pattern: str, test_text: str, result_label: Gtk.Label, 
                          validation_label: Gtk.Label):
        """Test a regex pattern against sample text."""
        import re
        
        if not pattern:
            result_label.set_markup(_("<span foreground='orange'>Enter a regex pattern first</span>"))
            return
        
        if not test_text:
            result_label.set_markup(_("<span foreground='orange'>Enter sample text to test</span>"))
            return
        
        # Validate first
        if not self.validate_regex(pattern, validation_label):
            result_label.set_markup(_("<span foreground='red'>Fix regex errors first</span>"))
            return
        
        try:
            regex = re.compile(pattern)
            matches = regex.findall(test_text)
            
            if matches:
                matches_str = ", ".join([f"'{m}'" for m in matches[:5]])
                if len(matches) > 5:
                    matches_str += _(" ... ({} total)").format(len(matches))
                result_label.set_markup(
                    _("<span foreground='green'>✓ Found {} match(es): {}</span>").format(len(matches), matches_str)
                )
            else:
                result_label.set_markup(
                    _("<span foreground='orange'>No matches found in test text</span>")
                )
        except Exception as e:
            result_label.set_markup(_("<span foreground='red'>Test error: {}</span>").format(e))
    
    def show_pattern_templates(self, entry: Gtk.Entry):
        """Show a popover with common regex pattern templates."""
        popover = Gtk.Popover()
        popover.set_parent(entry)
        popover.set_position(Gtk.PositionType.BOTTOM)
        
        # Scrolled window for templates
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_min_content_height(300)
        scrolled.set_max_content_height(500)
        scrolled.set_min_content_width(450)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        
        templates = [
            (_("Employee ID"), r"EMP-\d{6}", "EMP-123456"),
            (_("Project Code"), r"PROJ-[A-Z]{3}-\d{4}", "PROJ-ABC-1234"),
            (_("Account Number"), r"ACCT\d{10}", "ACCT1234567890"),
            (_("Internal IP"), r"10\.0\.\d{1,3}\.\d{1,3}", "10.0.1.100"),
            (_("Document ID"), r"DOC-[0-9A-F]{8}", "DOC-ABC12345"),
            (_("Serial Number"), r"SN[A-Z0-9]{12}", "SNABC123XYZ789"),
            (_("Phone (US)"), r"\d{3}-\d{3}-\d{4}", "555-123-4567"),
            (_("Email Domain"), r"@yourcompany\.com", "user@yourcompany.com"),
            (_("API Key Format"), r"sk_live_[a-zA-Z0-9]{24}", "sk_live_abc123xyz789def456ghi"),
            (_("UUID"), r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", 
             "550e8400-e29b-41d4-a716-446655440000"),
        ]
        
        title = Gtk.Label(label=_("Common Pattern Templates"))
        title.add_css_class("heading")
        title.set_margin_bottom(6)
        box.append(title)
        
        for name, pattern, example in templates:
            btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            btn_box.set_margin_bottom(8)
            
            btn = Gtk.Button(label=name)
            btn.add_css_class("flat")
            btn.set_can_focus(False)
            btn.set_halign(Gtk.Align.START)
            
            def on_template_click(widget, p=pattern, pop=popover):
                entry.set_text(p)
                pop.popdown()
            
            btn.connect("clicked", on_template_click)
            btn_box.append(btn)
            
            # Pattern display
            pattern_label = Gtk.Label(label=_("Pattern: {}").format(pattern), xalign=0, wrap=True)
            pattern_label.add_css_class("caption")
            pattern_label.set_margin_start(12)
            pattern_label.set_selectable(True)
            btn_box.append(pattern_label)
            
            # Example display
            example_label = Gtk.Label(label=_("Example: {}").format(example), xalign=0, wrap=True)
            example_label.add_css_class("caption")
            example_label.add_css_class("dim-label")
            example_label.set_margin_start(12)
            btn_box.append(example_label)
            
            box.append(btn_box)
        
        scrolled.set_child(box)
        popover.set_child(scrolled)
        popover.popup()
    
    def write_toml_manual(self, f, config: dict, indent: int = 0):
        """Simple TOML writer for basic configurations."""
        prefix = "  " * indent
        
        for key, value in config.items():
            if isinstance(value, dict):
                # Section header
                if indent == 0:
                    f.write(f"\n[{key}]\n")
                else:
                    f.write(f"\n{prefix}[{key}]\n")
                self.write_toml_manual(f, value, indent + 1)
            elif isinstance(value, list):
                # Array - always use repr for proper TOML formatting
                # Convert all items to proper TOML representation
                if len(value) == 0:
                    f.write(f'{prefix}{key} = []\n')
                elif all(isinstance(x, str) for x in value):
                    # String array
                    items = ', '.join(f'"{x}"' for x in value)
                    f.write(f'{prefix}{key} = [{items}]\n')
                elif all(isinstance(x, (int, float)) for x in value):
                    # Numeric array
                    items = ', '.join(str(x) for x in value)
                    f.write(f'{prefix}{key} = [{items}]\n')
                else:
                    # Mixed or complex types - use repr
                    f.write(f'{prefix}{key} = {repr(value)}\n')
            elif isinstance(value, bool):
                f.write(f'{prefix}{key} = {str(value).lower()}\n')
            elif isinstance(value, str):
                f.write(f'{prefix}{key} = "{value}"\n')
            elif isinstance(value, (int, float)):
                f.write(f'{prefix}{key} = {value}\n')
            else:
                f.write(f'{prefix}{key} = {repr(value)}\n')
    
    def on_help_clicked(self, button):
        """Open documentation browser."""
        docs = {
            _("Administration Guide"): "ADMINISTRATION.md",
            _("Content Scanning"): "CONTENT-SCANNING-INTEGRATION.md",
            _("File Type Support"): "FILE-TYPE-SUPPORT.md",
            _("Group Exemptions"): "GROUP-EXEMPTIONS.md",
            _("Notifications"): "NOTIFICATIONS.md",
            _("Main Documentation"): "USB-ENFORCER.md",
        }
        
        dialog = Gtk.Dialog()
        dialog.set_title(_("Documentation"))
        dialog.set_transient_for(self)
        dialog.set_modal(True)
        dialog.set_default_size(400, 300)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        
        label = Gtk.Label(label=_("Available Documentation"), xalign=0)
        label.add_css_class("title-2")
        box.append(label)
        
        for title, filename in docs.items():
            button = Gtk.Button(label=title)
            button.connect("clicked", lambda _, f=filename: self.open_documentation(f))
            box.append(button)
        
        dialog.set_child(box)
        dialog.present()
    
    def open_documentation(self, doc_path: str):
        """Display documentation in a dialog window."""
        # Try HTML first (if WebKit available), then fall back to markdown
        doc_base = doc_path.replace('.md', '')
        
        search_paths = []
        
        # If WebKit available, prefer HTML versions
        if WEBKIT_AVAILABLE:
            search_paths.extend([
                os.path.join("/usr/share/doc/usb-enforcer/html", doc_base + ".html"),
                os.path.join("/usr/share/doc/usb-enforcer/html", doc_base + ".html.gz"),
                os.path.join("/usr/share/doc/usb-enforcer", doc_base + ".html"),
                os.path.join("/usr/share/doc/usb-enforcer", doc_base + ".html.gz"),
            ])
        
        # Also check for markdown (with and without .gz)
        search_paths.extend([
            os.path.join("/usr/share/doc/usb-enforcer", doc_path),
            os.path.join("/usr/share/doc/usb-enforcer", doc_path + ".gz"),
            os.path.join("/usr/share/usb-enforcer", doc_path),
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", doc_path),
        ])
        
        full_path = None
        is_gzipped = False
        is_html = False
        for path in search_paths:
            if os.path.exists(path):
                full_path = path
                is_gzipped = path.endswith('.gz')
                is_html = '.html' in path
                break
        
        if not full_path:
            self.show_error(_("Documentation file not found: {}").format(doc_path))
            return
        
        try:
            if is_gzipped:
                import gzip
                with gzip.open(full_path, 'rt', encoding='utf-8') as f:
                    content = f.read()
            else:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            # Show documentation in a dialog
            if is_html and WEBKIT_AVAILABLE:
                # For HTML, pass the file path directly for proper navigation history
                self.show_html_documentation_dialog(os.path.basename(doc_base), full_path)
            else:
                self.show_documentation_dialog(os.path.basename(doc_path), content)
        except Exception as e:
            self.show_error(_("Error loading documentation: {}").format(e))
    
    def show_html_documentation_dialog(self, title: str, html_file_path: str):
        """Display HTML documentation using WebKit."""
        if not WEBKIT_AVAILABLE:
            # Fall back to plain text display
            self.show_error(_("WebKit not available for HTML display"))
            return
        
        dialog = Adw.Window()
        dialog.set_title(title)
        dialog.set_default_size(900, 700)
        dialog.set_transient_for(self)
        dialog.set_modal(True)
        
        # Main container
        toolbar_view = Adw.ToolbarView()
        
        # Header bar with navigation controls
        header = Adw.HeaderBar()
        
        # Back button
        back_button = Gtk.Button()
        back_button.set_icon_name("go-previous-symbolic")
        back_button.set_tooltip_text(_("Back"))
        back_button.set_sensitive(False)  # Initially disabled
        header.pack_start(back_button)
        
        # Forward button
        forward_button = Gtk.Button()
        forward_button.set_icon_name("go-next-symbolic")
        forward_button.set_tooltip_text(_("Forward"))
        forward_button.set_sensitive(False)  # Initially disabled
        header.pack_start(forward_button)
        
        toolbar_view.add_top_bar(header)
        
        # WebKit view for HTML content
        webview = WebKit.WebView()
        webview.set_vexpand(True)
        webview.set_hexpand(True)
        
        # Connect navigation buttons to WebKit
        def update_navigation_buttons(*args):
            back_button.set_sensitive(webview.can_go_back())
            forward_button.set_sensitive(webview.can_go_forward())
        
        back_button.connect("clicked", lambda b: webview.go_back())
        forward_button.connect("clicked", lambda b: webview.go_forward())
        
        # Update button states when navigation happens
        webview.connect("load-changed", update_navigation_buttons)
        
        # Load file directly via file:// URI for proper navigation history
        file_uri = f"file://{html_file_path}"
        webview.load_uri(file_uri)
        
        # Disable editing and context menu
        settings = webview.get_settings()
        settings.set_enable_write_console_messages_to_stdout(False)
        settings.set_enable_developer_extras(False)
        
        toolbar_view.set_content(webview)
        dialog.set_content(toolbar_view)
        
        dialog.present()
    
    def show_documentation_dialog(self, title: str, markdown_content: str):
        """Display documentation in a scrollable dialog."""
        dialog = Adw.Window()
        dialog.set_title(title)
        dialog.set_default_size(800, 600)
        dialog.set_transient_for(self)
        dialog.set_modal(True)
        
        # Main container
        toolbar_view = Adw.ToolbarView()
        
        # Header bar
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)
        
        # Scrolled window for content
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        
        # Text view for displaying documentation
        text_view = Gtk.TextView()
        text_view.set_editable(False)
        text_view.set_cursor_visible(False)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        text_view.set_left_margin(20)
        text_view.set_right_margin(20)
        text_view.set_top_margin(20)
        text_view.set_bottom_margin(20)
        
        # Parse and format the markdown content
        buffer = text_view.get_buffer()
        self._render_markdown_to_buffer(buffer, markdown_content)
        
        scrolled.set_child(text_view)
        toolbar_view.set_content(scrolled)
        dialog.set_content(toolbar_view)
        
        dialog.present()
    
    def _render_markdown_to_buffer(self, buffer: Gtk.TextBuffer, markdown_text: str):
        """Render markdown text to a GTK TextBuffer with formatting."""
        import re

        # Create text tags for formatting
        tag_h1 = buffer.create_tag("h1", scale=1.8, weight=700)
        tag_h2 = buffer.create_tag("h2", scale=1.5, weight=700)
        tag_h3 = buffer.create_tag("h3", scale=1.3, weight=700)
        tag_h4 = buffer.create_tag("h4", scale=1.1, weight=700)
        tag_bold = buffer.create_tag("bold", weight=700)
        tag_italic = buffer.create_tag("italic", style=Pango.Style.ITALIC)
        tag_code = buffer.create_tag("code", family="monospace", background="#f4f4f4")
        tag_code_block = buffer.create_tag("code_block", family="monospace", 
                                           background="#f4f4f4", left_margin=20, right_margin=20)
        tag_list = buffer.create_tag("list", left_margin=20)
        tag_quote = buffer.create_tag("quote", left_margin=20, right_margin=20,
                                      style=Pango.Style.ITALIC, foreground="#555555")
        tag_link = buffer.create_tag("link", underline=Pango.Underline.SINGLE,
                                     foreground="#1a73e8")
        
        lines = markdown_text.split('\n')
        in_code_block = False
        
        for line in lines:
            iter_end = buffer.get_end_iter()
            
            # Code blocks
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
                buffer.insert(iter_end, '\n')
                continue
            
            if in_code_block:
                iter_start = buffer.get_end_iter()
                buffer.insert(iter_end, line + '\n')
                iter_end = buffer.get_end_iter()
                buffer.apply_tag(tag_code_block, iter_start, iter_end)
                continue

            if not line.strip():
                buffer.insert(iter_end, '\n')
                continue
            
            # Headers
            if line.startswith('# '):
                iter_start = buffer.get_end_iter()
                buffer.insert(iter_end, line[2:] + '\n\n')
                iter_end = buffer.get_end_iter()
                buffer.apply_tag(tag_h1, iter_start, iter_end)
            elif line.startswith('## '):
                iter_start = buffer.get_end_iter()
                buffer.insert(iter_end, line[3:] + '\n\n')
                iter_end = buffer.get_end_iter()
                buffer.apply_tag(tag_h2, iter_start, iter_end)
            elif line.startswith('### '):
                iter_start = buffer.get_end_iter()
                buffer.insert(iter_end, line[4:] + '\n\n')
                iter_end = buffer.get_end_iter()
                buffer.apply_tag(tag_h3, iter_start, iter_end)
            elif line.startswith('#### '):
                iter_start = buffer.get_end_iter()
                buffer.insert(iter_end, line[5:] + '\n\n')
                iter_end = buffer.get_end_iter()
                buffer.apply_tag(tag_h4, iter_start, iter_end)
            else:
                unordered_match = re.match(r'^\s*[-*+]\s+(.*)', line)
                ordered_match = re.match(r'^\s*(\d+)\.\s+(.*)', line)
                quote_match = re.match(r'^\s*>\s?(.*)', line)

                if unordered_match:
                    iter_start = buffer.get_end_iter()
                    self._insert_formatted_line(
                        buffer,
                        f"• {unordered_match.group(1)}\n",
                        tag_bold,
                        tag_code,
                        tag_italic,
                        tag_link,
                    )
                    iter_end = buffer.get_end_iter()
                    buffer.apply_tag(tag_list, iter_start, iter_end)
                elif ordered_match:
                    iter_start = buffer.get_end_iter()
                    self._insert_formatted_line(
                        buffer,
                        f"{ordered_match.group(1)}. {ordered_match.group(2)}\n",
                        tag_bold,
                        tag_code,
                        tag_italic,
                        tag_link,
                    )
                    iter_end = buffer.get_end_iter()
                    buffer.apply_tag(tag_list, iter_start, iter_end)
                elif quote_match:
                    iter_start = buffer.get_end_iter()
                    self._insert_formatted_line(
                        buffer,
                        quote_match.group(1) + '\n',
                        tag_bold,
                        tag_code,
                        tag_italic,
                        tag_link,
                    )
                    iter_end = buffer.get_end_iter()
                    buffer.apply_tag(tag_quote, iter_start, iter_end)
                else:
                    # Process inline formatting (bold, italic, code, links)
                    self._insert_formatted_line(
                        buffer,
                        line + '\n',
                        tag_bold,
                        tag_code,
                        tag_italic,
                        tag_link,
                    )
    
    def _insert_formatted_line(self, buffer: Gtk.TextBuffer, line: str,
                               tag_bold: Gtk.TextTag, tag_code: Gtk.TextTag,
                               tag_italic: Gtk.TextTag, tag_link: Gtk.TextTag):
        """Insert a line with inline formatting (bold, italic, code, links)."""
        import re

        pattern = re.compile(
            r'`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|_[^_]+_|\[[^\]]+\]\([^)]+\)'
        )
        pos = 0

        for match in pattern.finditer(line):
            start, end = match.span()
            if start > pos:
                iter_end = buffer.get_end_iter()
                buffer.insert(iter_end, line[pos:start])

            token = match.group(0)
            if token.startswith('`'):
                text = token[1:-1]
                fmt = tag_code
            elif token.startswith('**'):
                text = token[2:-2]
                fmt = tag_bold
            elif token.startswith('*') or token.startswith('_'):
                text = token[1:-1]
                fmt = tag_italic
            elif token.startswith('['):
                link_match = re.match(r'^\[([^\]]+)\]\(([^)]+)\)$', token)
                if link_match:
                    text = f"{link_match.group(1)} ({link_match.group(2)})"
                    fmt = tag_link
                else:
                    text = token
                    fmt = None
            else:
                text = token
                fmt = None

            iter_start = buffer.get_end_iter()
            buffer.insert(iter_start, text)
            iter_end = buffer.get_end_iter()

            if fmt is not None:
                buffer.apply_tag(fmt, iter_start, iter_end)

            pos = end

        if pos < len(line):
            iter_end = buffer.get_end_iter()
            buffer.insert(iter_end, line[pos:])
    
    
    def show_help_popover(self, button: Gtk.Button, help_text: str):
        """Show help text in a popover."""
        popover = Gtk.Popover()
        popover.set_parent(button)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        
        label = Gtk.Label(label=help_text, wrap=True, xalign=0)
        label.set_max_width_chars(50)
        box.append(label)
        
        popover.set_child(box)
        popover.popup()
    
    def get_help_text(self, key: str) -> Optional[str]:
        """Get help text for a configuration key."""
        help_texts = {
            "enforce_on_usb_only": _("When enabled, only USB devices are enforced. Other storage types (SATA, NVMe, etc.) are not affected. Useful for workstations where internal drives should not be restricted."),
            "allow_luks1_readonly": _("LUKS1 is an older encryption format. If enabled, LUKS1 devices are allowed but only in read-only mode. LUKS2 is more secure and should be preferred."),
            "allow_luks2": _("When enabled, LUKS2 encrypted devices can be unlocked and used. LUKS2 is the modern Linux encryption standard with improved security. Disable to restrict only to VeraCrypt or other formats."),
            "allow_veracrypt": _("When enabled, VeraCrypt encrypted devices can be unlocked and used. VeraCrypt is cross-platform (Windows/Mac/Linux). Disable to restrict only to LUKS encryption."),
            "allow_plaintext_write_with_scanning": _("Allows writing to unencrypted USB drives if content scanning is enabled. Files are scanned for sensitive patterns before being written. Requires content_scanning_enabled=true."),
            "allow_group_exemption": _("Users in the configured exemption group can bypass enforcement. Useful for IT administrators or trusted users who need unrestricted access."),
            "exemption_group": _("Name of the system group whose members are exempt from enforcement. Default is 'usb-exempt'. Create this group and add trusted users to it."),
            "default_plain_mount_opts": _("Mount options for unencrypted USB devices, one per line. Common options:\n• nodev - No device files\n• nosuid - Ignore setuid bits\n• noexec - Prevent execution\n• ro - Read-only\nRecommended: nodev, nosuid, noexec, ro"),
            "default_encrypted_mount_opts": _("Mount options for encrypted USB devices, one per line. Common options:\n• nodev - No device files\n• nosuid - Ignore setuid bits\n• rw - Read-write access\nRecommended: nodev, nosuid, rw"),
            "require_noexec_on_plain": _("Enforce noexec flag on unencrypted USB drives. Prevents running executables from plaintext USB devices. Strongly recommended for security."),
            "read_only_mount": _("Forces all allowed devices to be mounted read-only. Prevents any writes even if the device would normally allow them. Highest security option."),
            "mount_options": _("Additional mount options passed to the kernel. Common options include 'noexec' (prevent execution), 'nosuid' (ignore setuid), 'nodev' (no device files)."),
            "default_encryption_type": _("Default encryption format for new USB devices. LUKS2 is Linux-only and recommended for Linux environments. VeraCrypt is cross-platform (Windows/Mac/Linux) but requires separate installation from https://www.veracrypt.fr"),
            "encryption_target_mode": _("Determines what gets encrypted. 'whole_disk' encrypts the entire device (recommended). 'partition' only encrypts a specific partition."),
            "filesystem_type": _("Filesystem created on encrypted devices. exfat is cross-platform. ext4 is Linux-native with journaling. ntfs is Windows-focused."),
            "luks2_cipher": _("Cipher algorithm for LUKS2 encryption. aes-xts-plain64 is recommended for modern systems. Options: aes-xts-plain64, aes-cbc-essiv, serpent-xts-plain64."),
            "luks2_key_size": _("Encryption key size in bits. 512 = 256-bit effective (XTS mode uses half for tweak). Larger is more secure but may be slightly slower."),
            "luks2_hash": _("Hash algorithm for key derivation. sha256 is standard, sha512 is more secure but slower. Options: sha256, sha512."),
            "luks2_pbkdf": _("Password-based key derivation function. argon2id is most secure (resistant to GPU attacks). Options: argon2id, argon2i, pbkdf2."),
            "luks2_pbkdf_time_ms": _("Time in milliseconds for key derivation. Higher values are more secure (slower brute force) but take longer to unlock. 2000ms is recommended."),
            "default_passphrase_length": _("Minimum length for auto-generated passphrases. Longer is more secure. 32 characters provides excellent security."),
            "content_scanning_enabled": _("Enables content scanning (DLP) to detect sensitive data patterns like SSNs, credit cards, etc. Requires patterns to be configured."),
            "scan_ssn": _("Detect US Social Security Numbers (XXX-XX-XXXX format)."),
            "scan_credit_card": _("Detect credit card numbers using Luhn algorithm validation."),
            "scan_email": _("Detect email addresses."),
            "scan_phone": _("Detect US phone numbers in various formats."),
            "scan_custom_patterns": _("Use custom regex patterns defined in the configuration."),
            "max_file_size_mb": _("Maximum size of files to scan. Larger files are skipped to prevent performance issues. 100MB is reasonable for most use cases."),
            "scan_timeout_seconds": _("Maximum time to spend scanning a single file. Prevents hangs on malformed files. 30 seconds is typical."),
            "scan_archives": _("Scan inside ZIP and other archive files. Increases scan time but catches hidden data."),
            "max_archive_depth": _("How many levels deep to scan nested archives. Prevents zip bombs. 3 levels is reasonable."),
            "ml_enabled": _("Use machine learning models for anomaly detection. Requires trained models to be present."),
        }
        return help_texts.get(key)
    
    def show_info(self, message: str):
        """Show info message."""
        self.info_bar.set_message_type(Gtk.MessageType.INFO)
        self.info_label.set_text(message)
        self.info_bar.set_visible(True)
    
    def show_success(self, message: str):
        """Show success message."""
        self.info_bar.set_message_type(Gtk.MessageType.INFO)
        self.info_label.set_text(message)
        self.info_bar.set_visible(True)
    
    def show_warning(self, message: str):
        """Show warning message."""
        self.info_bar.set_message_type(Gtk.MessageType.WARNING)
        self.info_label.set_text(message)
        self.info_bar.set_visible(True)
    
    def show_error(self, message: str):
        """Show error message."""
        self.info_bar.set_message_type(Gtk.MessageType.ERROR)
        self.info_label.set_text(message)
        self.info_bar.set_visible(True)


class AdminApp(Adw.Application):
    """Main application."""
    
    def __init__(self, config_path: Optional[str] = None):
        super().__init__(application_id="org.seravault.UsbEnforcerAdmin",
                        flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.config_path = config_path
        
        # Configure style manager to follow system theme (dark/light mode)
        style_manager = Adw.StyleManager.get_default()
        style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)  # Follow system preference
    
    def do_activate(self):
        win = AdminWindow(self, self.config_path)
        win.present()


def main():
    """Entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="USB Enforcer Administration GUI")
    parser.add_argument("--config", "-c", help="Path to config.toml file",
                       default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args()
    
    app = AdminApp(args.config)
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())

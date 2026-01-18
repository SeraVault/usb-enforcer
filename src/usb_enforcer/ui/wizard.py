from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Dict, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # type: ignore

try:
    import pydbus
except Exception:
    pydbus = None

try:
    import pyudev
except Exception:
    pyudev = None

from .. import secret_socket

BUS_NAME = "org.seravault.UsbEnforcer"
BUS_PATH = "/org/seravault/UsbEnforcer"


def get_mount_point(device_path: str) -> Optional[str]:
    """Get the mount point for a device by reading /proc/mounts."""
    try:
        with open("/proc/mounts", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == device_path:
                    # parts[1] is the mount point (may have escape sequences)
                    # Decode octal escapes like \040 for space
                    mount_point = parts[1]
                    mount_point = mount_point.replace("\\040", " ")
                    mount_point = mount_point.replace("\\011", "\t")
                    mount_point = mount_point.replace("\\012", "\n")
                    mount_point = mount_point.replace("\\134", "\\")
                    return mount_point
    except Exception as e:
        print(f"[get_mount_point] Error reading /proc/mounts: {e}")
    return None


def strength_color(length: int) -> str:
    if length >= 16:
        return "success"
    if length >= 12:
        return "warning"
    return "error"


class WizardWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Adw.Application, proxy, target_device: Optional[str] = None):
        super().__init__(application=app, title="USB Encryption Wizard")
        # Uniform window size - dropdown is compact either way
        self.set_default_size(520, 420)
        self.proxy = proxy
        self.target_device = target_device
        self.devices_cache: List[Dict[str, str]] = []
        
        # Header - use set_titlebar to replace the default title bar
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label="USB Encryption Wizard"))
        self.set_titlebar(header)
        
        # Content box with margins
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.content_box.set_margin_top(12)
        self.content_box.set_margin_bottom(12)
        self.content_box.set_margin_start(12)
        self.content_box.set_margin_end(12)
        self.set_child(self.content_box)

        # Device selection area
        device_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        device_label = Gtk.Label(label="USB Device to Encrypt", xalign=0)
        device_label.add_css_class("heading")
        device_box.append(device_label)
        
        # Create combo box for device selection
        self.device_store = Gio.ListStore.new(Gtk.StringObject)
        self.device_combo = Gtk.DropDown(model=self.device_store)
        self.device_combo.set_enable_search(False)
        self.device_combo.set_tooltip_text("Select a USB device to encrypt")
        device_box.append(self.device_combo)
        
        # Refresh button next to combo
        refresh_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        refresh_box.append(device_box)
        self.refresh_button = Gtk.Button(icon_name="view-refresh-symbolic")
        self.refresh_button.set_tooltip_text("Refresh device list")
        self.refresh_button.set_valign(Gtk.Align.END)
        self.refresh_button.connect("clicked", self.refresh_devices)
        refresh_box.append(self.refresh_button)
        
        self.content_box.append(refresh_box)

        # Encryption type selection
        encryption_type_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        encryption_type_label = Gtk.Label(label="Encryption Type", xalign=0)
        encryption_type_label.add_css_class("heading")
        encryption_type_box.append(encryption_type_label)
        
        self.encryption_type_store = Gio.ListStore.new(Gtk.StringObject)
        self.encryption_type_store.append(Gtk.StringObject.new("LUKS2 (Linux Unified Key Setup)"))
        
        # Check if VeraCrypt is installed
        import shutil
        veracrypt_available = shutil.which("veracrypt") is not None
        if veracrypt_available:
            self.encryption_type_store.append(Gtk.StringObject.new("VeraCrypt (Cross-platform)"))
        else:
            self.encryption_type_store.append(Gtk.StringObject.new("VeraCrypt (Not Installed)"))
        
        self.encryption_type_combo = Gtk.DropDown(model=self.encryption_type_store)
        
        # Load default encryption type from config
        default_type = self._load_default_encryption_type()
        default_idx = 0  # LUKS2
        if default_type == "veracrypt" and veracrypt_available:
            default_idx = 1
        self.encryption_type_combo.set_selected(default_idx)
        
        tooltip_text = "Select encryption format. "
        if not veracrypt_available:
            tooltip_text += "VeraCrypt is not installed. Install from https://www.veracrypt.fr for cross-platform support."
        else:
            tooltip_text += "LUKS2 for Linux-only, VeraCrypt for cross-platform (Windows, macOS, Linux)."
        self.encryption_type_combo.set_tooltip_text(tooltip_text)
        self.veracrypt_available = veracrypt_available
        
        encryption_type_box.append(self.encryption_type_combo)
        self.content_box.append(encryption_type_box)

        # Label field
        label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        label_label = Gtk.Label(label="Volume Label (optional)", xalign=0)
        self.label_entry = Gtk.Entry()
        self.label_entry.set_placeholder_text("Enter a label for the encrypted volume")
        self.label_entry.set_max_length(48)  # LUKS2 label max length
        label_box.append(label_label)
        label_box.append(self.label_entry)
        self.content_box.append(label_box)

        # Passphrase area
        passphrase_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        passphrase_label = Gtk.Label(label="Passphrase (min 12 chars)", xalign=0)
        self.pass_entry = Gtk.PasswordEntry(show_peek_icon=True)
        self.confirm_entry = Gtk.PasswordEntry(show_peek_icon=True)
        self.pass_strength = Gtk.LevelBar(min_value=0, max_value=20)
        self.pass_strength.set_value(0)
        self.pass_strength.add_offset_value("low", 10)
        self.pass_strength.add_offset_value("high", 16)
        passphrase_box.append(passphrase_label)
        passphrase_box.append(self.pass_entry)
        passphrase_box.append(Gtk.Label(label="Confirm", xalign=0))
        passphrase_box.append(self.confirm_entry)
        passphrase_box.append(self.pass_strength)
        self.content_box.append(passphrase_box)

        # Preserve data option
        self.preserve_data_check = Gtk.CheckButton(label="Preserve existing data (copy before encrypting)")
        self.preserve_data_check.set_margin_top(12)
        self.preserve_data_check.set_tooltip_text(
            "If checked, existing data will be copied to a temporary location, "
            "the drive will be encrypted, and data will be restored to the encrypted drive."
        )
        self.content_box.append(self.preserve_data_check)

        # Actions
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.encrypt_button = Gtk.Button(label="Encrypt", css_classes=["suggested-action"])
        actions.append(self.encrypt_button)
        self.content_box.append(actions)

        # Status
        self.progress = Gtk.ProgressBar(show_text=True)
        self.content_box.append(self.progress)

        self.encrypt_button.connect("clicked", self.on_encrypt)
        self.pass_entry.connect("changed", self.update_strength)

        if proxy:
            try:
                proxy.onEvent = self.on_event
                print(f"[WizardWindow] Subscribed to DBus Event signal")
            except Exception as e:
                print(f"[WizardWindow] Failed to subscribe to Event signal: {e}")
        self.refresh_devices()

    def update_strength(self, *_args):
        val = len(self.pass_entry.get_text())
        self.pass_strength.set_value(min(val, 20))
        css = strength_color(val)
        self.pass_strength.set_css_classes([css])

    def _load_default_encryption_type(self) -> str:
        """Load default encryption type from config file."""
        try:
            from ..config import Config
            config = Config.load()
            return config.default_encryption_type
        except Exception as e:
            print(f"[_load_default_encryption_type] Error loading config: {e}")
            return "luks2"  # Default fallback

    def notify(self, msg: str, level: str = "info"):
        # Show message in progress bar for now
        print(f"[WIZARD] {level.upper()}: {msg}")
        GLib.idle_add(self.progress.set_text, msg)
        # Could also show a dialog for errors
        if level == "error":
            def show_error():
                dialog = Gtk.MessageDialog(
                    transient_for=self,
                    modal=True,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text=msg
                )
                dialog.connect("response", lambda d, r: d.destroy())
                dialog.present()
            GLib.idle_add(show_error)

    def get_selected_device(self) -> Optional[Dict[str, str]]:
        # If target_device is set, return that device info directly
        if self.target_device:
            # Get the device from daemon
            try:
                devices = self.proxy.ListDevices()
                for dev in devices:
                    if dev.get("devnode") == self.target_device:
                        return dev
            except Exception:
                pass
            # Fallback: create minimal device info
            return {"devnode": self.target_device, "classification": "plaintext"}
        
        # Get selected device from dropdown
        selected_idx = self.device_combo.get_selected()
        if selected_idx != Gtk.INVALID_LIST_POSITION and selected_idx < len(self.devices_cache):
            return self.devices_cache[selected_idx]
        return None

    def refresh_devices(self, *_args):
        print("[refresh_devices] Starting device refresh...")
        self.devices_cache.clear()
        self.device_store.remove_all()
        
        try:
            devices = self.proxy.ListDevices()
            print(f"[refresh_devices] Got {len(devices)} devices from daemon: {devices}")
        except Exception as exc:
            print(f"[refresh_devices] Failed to list devices: {exc}")
            self.notify(f"Failed to list devices: {exc}", "error")
            return
        
        # Show parent disk devices instead of partitions for encryption
        # e.g., show /dev/sda instead of /dev/sda1
        device_paths = {dev.get("devnode") for dev in devices}
        print(f"[refresh_devices] Device paths: {device_paths}")
        
        # Group devices by parent disk
        parent_devices = {}
        for dev in devices:
            devnode = dev.get("devnode", "")
            # Check if this is a partition (ends with digit)
            if devnode and devnode[-1].isdigit():
                # Get parent device
                parent = devnode.rstrip("0123456789")
                if parent not in parent_devices:
                    # Store parent device info, prefer showing parent
                    parent_devices[parent] = dev.copy()
                    parent_devices[parent]["devnode"] = parent
            else:
                # This is already a parent device
                if devnode not in parent_devices:
                    parent_devices[devnode] = dev
        
        print(f"[refresh_devices] Parent devices: {parent_devices}")
        
        # If target_device is set, pre-select it and lock the combo
        if self.target_device:
            # Normalize target_device to parent disk if it's a partition
            lookup_device = self.target_device
            if lookup_device and lookup_device[-1].isdigit():
                # This is a partition, get parent device
                lookup_device = lookup_device.rstrip("0123456789")
            
            print(f"[refresh_devices] Target device mode: looking up {self.target_device}, normalized to {lookup_device}")
            dev_info = parent_devices.get(lookup_device)
            if dev_info:
                # Ensure devnode is parent disk
                dev_info_clean = dev_info.copy()
                dev_info_clean["devnode"] = lookup_device
                self.devices_cache.append(dev_info_clean)
                
                classification = dev_info.get("classification", "unknown")
                serial = dev_info.get("serial", "N/A")
                id_type = dev_info.get("id_type", "")
                display_text = f"{lookup_device} - {classification}"
                if id_type:
                    display_text += f" ({id_type})"
                
                self.device_store.append(Gtk.StringObject.new(display_text))
                self.device_combo.set_selected(0)
                self.device_combo.set_sensitive(False)  # Lock selection when device is specified
                self.refresh_button.set_sensitive(False)  # Disable refresh too
                print(f"[refresh_devices] Pre-selected target device: {lookup_device}")
            else:
                print(f"[refresh_devices] Warning: Target device {lookup_device} not found!")
                self.device_store.append(Gtk.StringObject.new(f"{self.target_device} (not found)"))
                self.device_combo.set_selected(0)
                self.device_combo.set_sensitive(False)
        else:
            # Show all available devices in dropdown
            for devnode, dev in sorted(parent_devices.items()):
                classification = dev.get("classification", "unknown")
                serial = dev.get("serial", "N/A")
                id_type = dev.get("id_type", "")
                
                # Only show plaintext devices (can be encrypted)
                if classification == "plaintext":
                    display_text = f"{devnode}"
                    if id_type:
                        display_text += f" - {id_type}"
                    if serial and serial != "N/A":
                        display_text += f" (Serial: {serial})"
                    
                    self.devices_cache.append(dev)
                    self.device_store.append(Gtk.StringObject.new(display_text))
                    print(f"[refresh_devices] Added device: {display_text}")
            
            # Select first device by default
            if len(self.devices_cache) > 0:
                self.device_combo.set_selected(0)
                print(f"[refresh_devices] Auto-selected first device")
            else:
                print(f"[refresh_devices] No plaintext devices available")
                self.device_store.append(Gtk.StringObject.new("No USB devices available for encryption"))
                self.device_combo.set_selected(0)
                self.device_combo.set_sensitive(False)

    def on_encrypt(self, _btn):
        print("[on_encrypt] Encrypt button clicked")
        dev = self.get_selected_device()
        print(f"[on_encrypt] Selected device: {dev}")
        if not dev:
            self.notify("Select a device to encrypt", "error")
            return
        classification = dev.get("classification")
        print(f"[on_encrypt] Device classification: {classification}")
        if classification not in ("plaintext",):
            self.notify(f"Only plaintext devices can be encrypted (current: {classification})", "error")
            return
        pwd = self.pass_entry.get_text()
        confirm = self.confirm_entry.get_text()
        print(f"[on_encrypt] Password length: {len(pwd)}, Confirm length: {len(confirm)}, Match: {pwd == confirm}")
        if pwd != confirm or len(pwd) < 12:
            self.notify("Passphrases must match and be at least 12 characters", "error")
            return
        
        # Device should already be parent device from refresh_devices
        devnode = dev["devnode"]
        mapper = devnode.split("/")[-1]
        preserve_data = self.preserve_data_check.get_active()
        label = self.label_entry.get_text().strip() or None
        
        # Get selected encryption type
        encryption_type_idx = self.encryption_type_combo.get_selected()
        encryption_type = "luks2" if encryption_type_idx == 0 else "veracrypt"
        
        # Validate VeraCrypt is available if selected
        if encryption_type == "veracrypt" and not self.veracrypt_available:
            self.notify("VeraCrypt is not installed. Please install it or use LUKS2.", "error")
            return
        
        print(f"[on_encrypt] Starting encryption thread for {devnode}, mapper={mapper}, preserve_data={preserve_data}, label={label}, type={encryption_type}")
        threading.Thread(target=self._encrypt_thread, args=(devnode, mapper, pwd, preserve_data, label, encryption_type), daemon=True).start()

    def _encrypt_thread(self, devnode: str, mapper: str, password: str, preserve_data: bool = False, label: Optional[str] = None, encryption_type: str = "luks2"):
        temp_dir = None
        mount_point = None
        
        try:
            # Step 1: Backup data if requested
            if preserve_data:
                GLib.idle_add(self.progress.set_fraction, 0.05)
                GLib.idle_add(self.progress.set_text, "Mounting device to backup data...")
                
                # Find if device has partitions or use the device itself
                target_device = self._find_mountable_partition(devnode)
                
                # Create temp directory for backup
                temp_dir = tempfile.mkdtemp(prefix="usb_backup_")
                print(f"[_encrypt_thread] Created temp directory: {temp_dir}")
                
                # Check if device is already mounted, or mount it
                mount_point = None
                we_mounted = False
                
                # Check if already mounted by reading /proc/mounts
                mount_point = get_mount_point(target_device)
                if mount_point:
                    print(f"[_encrypt_thread] Device already mounted at {mount_point}")
                
                # If not mounted, mount it now
                if not mount_point:
                    try:
                        result = subprocess.run(
                            ["udisksctl", "mount", "-b", target_device],
                            check=True,
                            capture_output=True,
                            text=True
                        )
                        we_mounted = True
                        
                        # Get mount point from /proc/mounts instead of parsing output
                        mount_point = get_mount_point(target_device)
                        if not mount_point:
                            raise Exception("Device mounted but could not find mount point")
                        
                        print(f"[_encrypt_thread] Mounted {target_device} at {mount_point}")
                    except subprocess.CalledProcessError as e:
                        # Check if error is "already mounted"
                        error_msg = e.stderr if e.stderr else str(e)
                        if "already mounted" in error_msg.lower():
                            # Try to find the mount point from /proc/mounts
                            mount_point = get_mount_point(target_device)
                            if mount_point:
                                print(f"[_encrypt_thread] Device was already mounted at {mount_point}")
                            else:
                                raise Exception(f"Device already mounted but could not find mount point")
                        else:
                            raise Exception(f"Failed to mount device: {error_msg}")
                    except FileNotFoundError:
                        raise Exception("udisksctl not found - please install udisks2")
                
                # Copy data
                GLib.idle_add(self.progress.set_fraction, 0.1)
                GLib.idle_add(self.progress.set_text, "Backing up data...")
                
                try:
                    # Use rsync for better progress, fallback to cp
                    if shutil.which("rsync"):
                        subprocess.run(
                            ["rsync", "-a", "--info=progress2", f"{mount_point}/", f"{temp_dir}/"],
                            check=True,
                            capture_output=True
                        )
                    else:
                        shutil.copytree(mount_point, temp_dir, dirs_exist_ok=True, copy_function=shutil.copy2)
                    print(f"[_encrypt_thread] Data backed up to {temp_dir}")
                except Exception as e:
                    raise Exception(f"Failed to backup data: {e}")
                
                # Unmount using udisksctl (only if we mounted it)
                GLib.idle_add(self.progress.set_fraction, 0.2)
                GLib.idle_add(self.progress.set_text, "Unmounting device...")
                if we_mounted:
                    try:
                        subprocess.run(["udisksctl", "unmount", "-b", target_device], check=True, capture_output=True)
                        print(f"[_encrypt_thread] Unmounted {target_device}")
                    except subprocess.CalledProcessError as e:
                        # Non-critical, continue anyway
                        print(f"[_encrypt_thread] Warning: Failed to unmount: {e}")
                else:
                    print(f"[_encrypt_thread] Skipping unmount (device was already mounted when we started)")
            
            # Step 2: Encrypt the device
            GLib.idle_add(self.progress.set_fraction, 0.25)
            GLib.idle_add(self.progress.set_text, f"Starting {encryption_type.upper()} encryption...")
            token = secret_socket.send_secret("encrypt", devnode, password, mapper)
            # Pass encryption_type via the config; for now we'll use the label field to pass it
            # Format: "label|encryption_type" or just "label" for default LUKS2
            label_with_type = f"{label or ''}|{encryption_type}"
            self.proxy.RequestEncrypt(devnode, mapper, token, "exfat", label_with_type)
            
            # Wait for encryption to complete (monitor via events)
            # The on_event handler will update progress
            import time
            max_wait = 300  # 5 minutes timeout
            waited = 0
            encryption_done = False
            
            while waited < max_wait and not encryption_done:
                time.sleep(1)
                waited += 1
                # Check if mapper device exists (indicates encryption completed)
                mapper_path = f"/dev/mapper/{mapper}"
                if os.path.exists(mapper_path):
                    encryption_done = True
                    break
            
            if not encryption_done:
                raise Exception("Encryption timeout - device may still be encrypting")
            
            # Step 3: Restore data if we backed it up
            if preserve_data and temp_dir:
                GLib.idle_add(self.progress.set_fraction, 0.85)
                GLib.idle_add(self.progress.set_text, "Waiting for encrypted device...")
                
                mapper_path = f"/dev/mapper/{mapper}"
                encrypted_mount = None
                
                # Wait for the daemon to auto-mount the device (up to 10 seconds)
                max_mount_wait = 10
                for i in range(max_mount_wait):
                    time.sleep(1)
                    encrypted_mount = get_mount_point(mapper_path)
                    if encrypted_mount:
                        print(f"[_encrypt_thread] Daemon auto-mounted at {encrypted_mount}")
                        break
                
                # If not auto-mounted, try to mount it ourselves
                if not encrypted_mount:
                    print(f"[_encrypt_thread] Device not auto-mounted, attempting manual mount")
                    try:
                        result = subprocess.run(
                            ["udisksctl", "mount", "-b", mapper_path],
                            check=True,
                            capture_output=True,
                            text=True
                        )
                        encrypted_mount = get_mount_point(mapper_path)
                        if not encrypted_mount:
                            raise Exception("Device mounted but could not find mount point")
                    except subprocess.CalledProcessError as e:
                        error_msg = e.stderr if e.stderr else str(e)
                        raise Exception(f"Failed to mount encrypted device: {error_msg}")
                
                print(f"[_encrypt_thread] Mounted encrypted device at {encrypted_mount}")
                
                # Restore data
                GLib.idle_add(self.progress.set_fraction, 0.9)
                GLib.idle_add(self.progress.set_text, "Restoring data...")
                
                try:
                    # Copy files back
                    for item in os.listdir(temp_dir):
                        src = os.path.join(temp_dir, item)
                        dst = os.path.join(encrypted_mount, item)
                        if os.path.isdir(src):
                            shutil.copytree(src, dst)
                        else:
                            shutil.copy2(src, dst)
                    print(f"[_encrypt_thread] Data restored to encrypted device")
                except Exception as e:
                    # Don't fail completely if restore has issues
                    GLib.idle_add(self.notify, f"Warning: Data restore incomplete: {e}", "warning")
                
                # Sync filesystem to ensure all data is written
                subprocess.run(["sync"], check=False)
                
                # Leave the device mounted for user convenience - no unmount to avoid auth prompt
                # The device was auto-mounted by the daemon and contains the restored data
                print(f"[_encrypt_thread] Leaving device mounted at {encrypted_mount} for user access")
            
            # Success
            GLib.idle_add(self.progress.set_fraction, 1.0)
            if preserve_data:
                GLib.idle_add(self.progress.set_text, "Encryption complete - Data restored")
                GLib.idle_add(self.notify, f"Encryption complete with data preserved: {devnode}")
            else:
                GLib.idle_add(self.progress.set_text, "Encryption complete")
                GLib.idle_add(self.notify, f"Encryption complete: {devnode}")
            
            # Close the wizard after 3 seconds
            GLib.timeout_add_seconds(3, self.close)
            
        except Exception as exc:
            print(f"[_encrypt_thread] Error: {exc}")
            GLib.idle_add(self.notify, f"Encrypt failed: {exc}", "error")
            GLib.idle_add(self.progress.set_fraction, 0.0)
            GLib.idle_add(self.progress.set_text, "Encryption failed")
        
        finally:
            # Cleanup temp directories
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    print(f"[_encrypt_thread] Cleaned up temp directory: {temp_dir}")
                except Exception as e:
                    print(f"[_encrypt_thread] Failed to cleanup temp dir: {e}")
            
            if mount_point and os.path.exists(mount_point):
                try:
                    # mount_point might be managed by udisks, just try to clean temp dirs
                    # Don't try to unmount as udisksctl already handled it
                    if mount_point.startswith('/tmp/'):
                        os.rmdir(mount_point)
                        print(f"[_encrypt_thread] Cleaned up temp mount point: {mount_point}")
                except Exception as e:
                    print(f"[_encrypt_thread] Failed to cleanup mount point: {e}")
    
    def _find_mountable_partition(self, devnode: str) -> str:
        """Find the first mountable partition on a device using pyudev."""
        # If the devnode itself is a partition (ends with digit), return it
        if devnode and devnode[-1].isdigit():
            print(f"[_find_mountable_partition] Device is already a partition: {devnode}")
            return devnode
        
        # Use pyudev to find partitions
        if pyudev:
            try:
                context = pyudev.Context()
                device = pyudev.Devices.from_device_file(context, devnode)
                
                # Iterate through children to find partitions
                for child in context.list_devices(parent=device):
                    if child.device_type == 'partition' and child.device_node:
                        partition = child.device_node
                        print(f"[_find_mountable_partition] Found partition via pyudev: {partition}")
                        return partition
            except Exception as e:
                print(f"[_find_mountable_partition] Error using pyudev: {e}")
        
        # Fallback: check /sys/block for partitions
        try:
            device_name = os.path.basename(devnode)
            sys_path = f"/sys/block/{device_name}"
            
            if os.path.exists(sys_path):
                # Look for partition subdirectories (e.g., sdb1, sdb2)
                for entry in os.listdir(sys_path):
                    if entry.startswith(device_name) and entry[len(device_name):].lstrip('p').isdigit():
                        partition = f"/dev/{entry}"
                        if os.path.exists(partition):
                            print(f"[_find_mountable_partition] Found partition via sysfs: {partition}")
                            return partition
        except Exception as e:
            print(f"[_find_mountable_partition] Error checking sysfs: {e}")
        
        # Return the device itself as final fallback
        print(f"[_find_mountable_partition] No partition found, using device: {devnode}")
        return devnode

    def on_unlock(self, _btn):
        dev = self.get_selected_device()
        if not dev:
            self.notify("Select a device to unlock", "error")
            return
        if dev.get("classification") not in ("luks2_locked", "veracrypt_locked"):
            self.notify("Only encrypted devices can be unlocked", "error")
            return
        pwd = self.pass_entry.get_text()
        if len(pwd) < 1:
            self.notify("Enter passphrase to unlock", "error")
            return
        mapper = dev["devnode"].split("/")[-1]
        threading.Thread(target=self._unlock_thread, args=(dev["devnode"], mapper, pwd), daemon=True).start()

    def _unlock_thread(self, devnode: str, mapper: str, password: str):
        GLib.idle_add(self.progress.set_fraction, 0.1)
        GLib.idle_add(self.progress.set_text, "Unlocking...")
        try:
            token = secret_socket.send_secret("unlock", devnode, password, mapper)
            self.proxy.RequestUnlock(devnode, mapper, token)
            GLib.idle_add(self.progress.set_fraction, 1.0)
            GLib.idle_add(self.progress.set_text, "Unlock requested; watch notifications")
        except Exception as exc:
            GLib.idle_add(self.notify, f"Unlock failed: {exc}", "error")

    def on_event(self, fields):
        # DBus signal callback
        print(f"[on_event] Received event: {fields}")
        action = fields.get("ACTION", "")
        devnode = fields.get("DEVNODE", "")
        progress = fields.get("PROGRESS", "")
        print(f"[on_event] action={action} devnode={devnode} progress={progress}")
        if action.startswith("encrypt_"):
            print(f"[on_event] Updating encryption progress: {progress}%")
            GLib.idle_add(self.progress.set_text, f"Encrypting {devnode} ({progress}%)")
            try:
                pct = float(progress) / 100.0 if progress else 0
                GLib.idle_add(self.progress.set_fraction, pct)
            except Exception as e:
                print(f"[on_event] Error setting progress: {e}")
        elif action == "encrypt_done":
            print(f"[on_event] Encryption complete")
            # Don't send notification here - already sent by _encrypt_thread
            GLib.idle_add(self.progress.set_fraction, 1.0)
            GLib.idle_add(self.progress.set_text, "Encryption complete")
            # Close the wizard after 2 seconds
            GLib.timeout_add_seconds(2, self.close)
        elif action == "encrypt_fail":
            print(f"[on_event] Encryption failed")
            GLib.idle_add(self.notify, f"Encryption failed: {devnode}", "error")
            GLib.idle_add(self.progress.set_fraction, 0.0)
        elif action == "unlock_done":
            GLib.idle_add(self.notify, f"Unlocked: {devnode}")
        elif action == "unlock_fail":
            GLib.idle_add(self.notify, f"Unlock failed: {devnode}", "error")


class WizardApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="com.seravault.usb.encryption.wizard",
            flags=Gio.ApplicationFlags.NON_UNIQUE  # Allow multiple instances
        )
        self.proxy = None
        self.target_device = None

    def do_activate(self):
        print("[WizardApp] do_activate called")
        if not pydbus:
            print("ERROR: pydbus is not installed. Install pydbus to use the wizard.")
            self.quit()
            return
        try:
            self.proxy = pydbus.SystemBus().get(BUS_NAME, BUS_PATH)
            print(f"[WizardApp] Connected to daemon successfully")
        except Exception as exc:
            print(f"ERROR: Could not connect to {BUS_NAME}: {exc}")
            self.quit()
            return
        print(f"[WizardApp] Creating wizard window for device: {self.target_device}...")
        wizard_win = WizardWindow(self, self.proxy, self.target_device)
        print(f"[WizardApp] Window created, calling present()...")
        wizard_win.present()
        print(f"[WizardApp] Window presented")


def main():
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="USB Encryption Wizard")
    parser.add_argument("--device", help="Target device to encrypt (e.g., /dev/sda)")
    args = parser.parse_args()
    
    print(f"[main] Starting wizard application for device: {args.device}...", file=sys.stderr, flush=True)
    try:
        app = WizardApp()
        app.target_device = args.device
        print("[main] WizardApp instance created", file=sys.stderr, flush=True)
        result = app.run(sys.argv[:1])  # Don't pass --device to GTK
        print(f"[main] app.run() returned: {result}", file=sys.stderr, flush=True)
        return result
    except Exception as e:
        print(f"[main] FATAL ERROR: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    main()

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

BUS_NAME = "org.seravault.UsbEncryptionEnforcer"
BUS_PATH = "/org/seravault/UsbEncryptionEnforcer"


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


class DeviceRow(Adw.ActionRow):
    def __init__(self, device: Dict[str, str]):
        super().__init__()
        self.device = device
        self.set_title(device.get("devnode", "unknown"))
        subtitle = f"{device.get('classification', 'unknown')} {device.get('id_type', '')}".strip()
        self.set_subtitle(subtitle)
        self.set_activatable(True)
        self.checkbox = Gtk.CheckButton()
        self.add_prefix(self.checkbox)

    def set_active(self, active: bool):
        self.checkbox.set_active(active)

    def get_active(self) -> bool:
        return self.checkbox.get_active()


class WizardWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Adw.Application, proxy, target_device: Optional[str] = None):
        super().__init__(application=app, title="USB Encryption Wizard")
        # Adjust window size based on whether we're showing device selection
        if target_device:
            self.set_default_size(520, 400)  # Smaller since no device list
        else:
            self.set_default_size(520, 600)  # Larger with device list
        self.proxy = proxy
        self.selected_row: Optional[DeviceRow] = None
        self.target_device = target_device
        
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

        # Device info label (shown when target_device is set)
        self.device_info_label = Gtk.Label(xalign=0)
        self.device_info_label.set_markup("<b>Device:</b> Loading...")
        self.device_info_label.set_margin_bottom(12)
        
        self.device_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.device_list.add_css_class("boxed-list")
        self.device_list.connect("row-activated", self.on_row_activated)
        
        # Wrap device list in a scrolled window
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_child(self.device_list)
        self.scrolled.set_vexpand(True)
        self.scrolled.set_min_content_height(150)
        
        # Only show device list or info label based on target_device
        if self.target_device:
            self.content_box.append(self.device_info_label)
        else:
            self.content_box.append(self.scrolled)

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
        self.refresh_button = Gtk.Button(label="Refresh")
        actions.append(self.encrypt_button)
        # Only show refresh button if not in target_device mode
        if not self.target_device:
            actions.append(self.refresh_button)
        self.content_box.append(actions)

        # Status
        self.progress = Gtk.ProgressBar(show_text=True)
        self.content_box.append(self.progress)

        self.encrypt_button.connect("clicked", self.on_encrypt)
        self.refresh_button.connect("clicked", self.refresh_devices)
        self.pass_entry.connect("changed", self.update_strength)

        if proxy:
            try:
                proxy.onEvent = self.on_event
                print(f"[WizardWindow] Subscribed to DBus Event signal")
            except Exception as e:
                print(f"[WizardWindow] Failed to subscribe to Event signal: {e}")
        self.refresh_devices()

    def on_row_activated(self, _listbox, row):
        if isinstance(row, DeviceRow):
            if self.selected_row:
                self.selected_row.set_active(False)
            row.set_active(True)
            self.selected_row = row

    def update_strength(self, *_args):
        val = len(self.pass_entry.get_text())
        self.pass_strength.set_value(min(val, 20))
        css = strength_color(val)
        self.pass_strength.set_css_classes([css])

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
        
        if self.selected_row:
            return self.selected_row.device
        return None

    def refresh_devices(self, *_args):
        print("[refresh_devices] Starting device refresh...")
        self.device_list.remove_all()
        self.selected_row = None
        try:
            devices = self.proxy.ListDevices()
            print(f"[refresh_devices] Got {len(devices)} devices from daemon: {devices}")
        except Exception as exc:
            print(f"[refresh_devices] Failed to list devices: {exc}")
            self.notify(f"Failed to list devices: {exc}", "error")
            return
        
        # Show parent disk devices instead of partitions for encryption
        # e.g., show /dev/sda instead of /dev/sda1
        filtered_devices = []
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
        
        # If target_device is set, update the info label instead of showing list
        if self.target_device:
            # Normalize target_device to parent disk if it's a partition
            lookup_device = self.target_device
            if lookup_device and lookup_device[-1].isdigit():
                # This is a partition, get parent device
                lookup_device = lookup_device.rstrip("0123456789")
            
            print(f"[refresh_devices] Looking up target_device={self.target_device}, normalized to {lookup_device}")
            print(f"[refresh_devices] Available parent devices: {list(parent_devices.keys())}")
            dev_info = parent_devices.get(lookup_device)
            if dev_info:
                classification = dev_info.get("classification", "unknown")
                serial = dev_info.get("serial", "")
                info_text = f"<b>Device:</b> {lookup_device}\n<b>Type:</b> {classification}"
                if serial:
                    info_text += f"\n<b>Serial:</b> {serial}"
                self.device_info_label.set_markup(info_text)
                # Set this as selected device - create a clean copy with parent devnode
                self.selected_row = type('obj', (object,), {
                    'device': {
                        'devnode': lookup_device,  # Use parent disk explicitly
                        'classification': classification,
                        'serial': serial,
                        'id_bus': dev_info.get('id_bus'),
                        'id_type': dev_info.get('id_type'),
                    }
                })()
                print(f"[refresh_devices] Selected device will use devnode: {lookup_device}")
            else:
                print(f"[refresh_devices] Lookup failed! {lookup_device} not in parent_devices")
                self.device_info_label.set_markup(f"<b>Device:</b> {lookup_device}\n<i>Device not found in daemon cache</i>")
        else:
            # Show device list as before
            for devnode, dev in parent_devices.items():
                print(f"[refresh_devices] Adding device: {dev}")
                row = DeviceRow(dev)
                self.device_list.append(row)
                filtered_devices.append(dev)

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
        print(f"[on_encrypt] Starting encryption thread for {devnode}, mapper={mapper}, preserve_data={preserve_data}")
        threading.Thread(target=self._encrypt_thread, args=(devnode, mapper, pwd, preserve_data), daemon=True).start()

    def _encrypt_thread(self, devnode: str, mapper: str, password: str, preserve_data: bool = False):
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
            GLib.idle_add(self.progress.set_text, "Starting encryption...")
            token = secret_socket.send_secret("encrypt", devnode, password, mapper)
            self.proxy.RequestEncrypt(devnode, mapper, token, "exfat", "")
            
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
        if dev.get("classification") not in ("luks2_locked",):
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

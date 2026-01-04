from __future__ import annotations

import threading
from typing import Dict, List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # type: ignore

try:
    import pydbus
except Exception:
    pydbus = None

BUS_NAME = "org.seravault.UsbEncryptionEnforcer"
BUS_PATH = "/org/seravault/UsbEncryptionEnforcer"


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
    def __init__(self, app: Adw.Application, proxy):
        super().__init__(application=app, title="USB Encryption Wizard")
        self.set_default_size(520, 600)
        self.proxy = proxy
        self.selected_row: Optional[DeviceRow] = None
        
        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(main_box)
        
        # Header
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label="USB Encryption Wizard"))
        main_box.append(header)
        
        # Content box with margins
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.content_box.set_margin_top(12)
        self.content_box.set_margin_bottom(12)
        self.content_box.set_margin_start(12)
        self.content_box.set_margin_end(12)
        main_box.append(self.content_box)

        self.device_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.device_list.add_css_class("boxed-list")
        self.device_list.connect("row-activated", self.on_row_activated)
        
        # Wrap device list in a scrolled window
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(self.device_list)
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(150)
        self.content_box.append(scrolled)

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

        # Actions
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.encrypt_button = Gtk.Button(label="Encrypt", css_classes=["suggested-action"])
        self.unlock_button = Gtk.Button(label="Unlock")
        self.refresh_button = Gtk.Button(label="Refresh")
        actions.append(self.encrypt_button)
        actions.append(self.unlock_button)
        actions.append(self.refresh_button)
        self.content_box.append(actions)

        # Status
        self.progress = Gtk.ProgressBar(show_text=True)
        self.content_box.append(self.progress)

        self.encrypt_button.connect("clicked", self.on_encrypt)
        self.unlock_button.connect("clicked", self.on_unlock)
        self.refresh_button.connect("clicked", self.refresh_devices)
        self.pass_entry.connect("changed", self.update_strength)

        if proxy:
            try:
                proxy.onEvent = self.on_event
            except Exception:
                pass
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
        print(f"[on_encrypt] Starting encryption thread for {devnode}, mapper={mapper}")
        threading.Thread(target=self._encrypt_thread, args=(devnode, mapper, pwd), daemon=True).start()

    def _encrypt_thread(self, devnode: str, mapper: str, password: str):
        GLib.idle_add(self.progress.set_fraction, 0.1)
        GLib.idle_add(self.progress.set_text, "Encrypting...")
        try:
            self.proxy.RequestEncrypt(devnode, mapper, password, "ext4", "")
            GLib.idle_add(self.progress.set_fraction, 1.0)
            GLib.idle_add(self.progress.set_text, "Encryption started; watch notifications")
        except Exception as exc:
            GLib.idle_add(self.notify, f"Encrypt failed: {exc}", "error")

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
            self.proxy.RequestUnlock(devnode, mapper, password)
            GLib.idle_add(self.progress.set_fraction, 1.0)
            GLib.idle_add(self.progress.set_text, "Unlock requested; watch notifications")
        except Exception as exc:
            GLib.idle_add(self.notify, f"Unlock failed: {exc}", "error")

    def on_event(self, fields):
        # DBus signal callback
        action = fields.get("ACTION", "")
        devnode = fields.get("DEVNODE", "")
        progress = fields.get("PROGRESS", "")
        if action.startswith("encrypt_"):
            GLib.idle_add(self.progress.set_text, f"Encrypting {devnode} ({progress}%)")
            try:
                pct = float(progress) / 100.0 if progress else 0
                GLib.idle_add(self.progress.set_fraction, pct)
            except Exception:
                pass
        elif action == "encrypt_done":
            GLib.idle_add(self.notify, f"Encryption complete: {devnode}")
            GLib.idle_add(self.progress.set_fraction, 1.0)
        elif action == "encrypt_fail":
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
        print("[WizardApp] Creating wizard window...")
        wizard_win = WizardWindow(self, self.proxy)
        print(f"[WizardApp] Window created, calling present()...")
        wizard_win.present()
        print(f"[WizardApp] Window presented")


def main():
    import sys
    print("[main] Starting wizard application...", file=sys.stderr, flush=True)
    try:
        app = WizardApp()
        print("[main] WizardApp instance created", file=sys.stderr, flush=True)
        result = app.run(sys.argv)
        print(f"[main] app.run() returned: {result}", file=sys.stderr, flush=True)
        return result
    except Exception as e:
        print(f"[main] FATAL ERROR: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    main()

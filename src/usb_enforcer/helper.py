"""Helper script for USB encryption operations"""
import sys
import subprocess
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
from usb_enforcer import secret_socket


def show_unlock_dialog(devnode):
    """Show a dialog to unlock an encrypted device"""
    class UnlockDialog(Gtk.ApplicationWindow):
        def __init__(self, app):
            super().__init__(application=app, title=f"Unlock {devnode}")
            self.devnode = devnode
            self.set_default_size(400, 200)
            
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_margin_top(12)
            box.set_margin_bottom(12)
            box.set_margin_start(12)
            box.set_margin_end(12)
            self.set_child(box)
            
            label = Gtk.Label(label=f"Enter passphrase to unlock {devnode}:")
            box.append(label)
            
            self.passphrase_entry = Gtk.PasswordEntry()
            self.passphrase_entry.set_show_peek_icon(True)
            self.passphrase_entry.connect("activate", self.on_unlock)
            box.append(self.passphrase_entry)
            
            self.status_label = Gtk.Label()
            box.append(self.status_label)
            
            button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            button_box.set_halign(Gtk.Align.END)
            box.append(button_box)
            
            cancel_btn = Gtk.Button(label="Cancel")
            cancel_btn.connect("clicked", lambda _: app.quit())
            button_box.append(cancel_btn)
            
            unlock_btn = Gtk.Button(label="Unlock")
            unlock_btn.add_css_class("suggested-action")
            unlock_btn.connect("clicked", self.on_unlock)
            button_box.append(unlock_btn)
        
        def on_unlock(self, widget):
            passphrase = self.passphrase_entry.get_text()
            if not passphrase:
                self.status_label.set_text("Please enter a passphrase")
                return
            
            self.status_label.set_text("Unlocking...")
            GLib.idle_add(self.do_unlock, passphrase)
        
        def do_unlock(self, passphrase):
            try:
                import pydbus
                bus = pydbus.SystemBus()
                proxy = bus.get("org.seravault.UsbEnforcer", "/org/seravault/UsbEnforcer")
                token = secret_socket.send_secret("unlock", self.devnode, passphrase)
                result = proxy.RequestUnlock(self.devnode, "", token)
                self.status_label.set_text(f"Unlocked: {result}")
                GLib.timeout_add(1000, self.get_application().quit)
            except Exception as e:
                self.status_label.set_text(f"Error: {str(e)}")
            return False
    
    class UnlockApp(Gtk.Application):
        def do_activate(self):
            win = UnlockDialog(self)
            win.present()
    
    app = UnlockApp()
    app.run(None)


def set_readonly(devnode):
    """Set device to read-only"""
    import os
    block_name = os.path.basename(devnode)
    sysfs_ro = f"/sys/class/block/{block_name}/ro"
    if os.path.exists(sysfs_ro):
        with open(sysfs_ro, 'w') as f:
            f.write('1')


def main():
    if len(sys.argv) < 3:
        print(f"usage: {sys.argv[0]} <unlock|ro> <devnode>", file=sys.stderr)
        sys.exit(1)
    
    action = sys.argv[1]
    devnode = sys.argv[2]
    
    if action == "unlock":
        show_unlock_dialog(devnode)
    elif action == "ro":
        set_readonly(devnode)
    else:
        print(f"unsupported action: {action}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

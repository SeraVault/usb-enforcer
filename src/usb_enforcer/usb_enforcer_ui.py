"""
User-session bridge: listens for DBus Event signals and shows desktop notifications.
This is intentionally minimal; replace with full GTK UI for production.
"""
import subprocess
import sys
import time
from typing import Dict, Callable, Optional

try:
    import pydbus
    from gi.repository import GLib  # type: ignore
except Exception:
    print("pydbus / pygobject not installed; UI bridge inactive")
    raise SystemExit(0)

from usb_enforcer.i18n import _, ngettext

BUS_NAME = "org.seravault.UsbEnforcer"
BUS_PATH = "/org/seravault/UsbEnforcer"
NOTIFY_BUS = "org.freedesktop.Notifications"
NOTIFY_PATH = "/org/freedesktop/Notifications"


class NotificationManager:
    def __init__(self):
        self.bus = pydbus.SessionBus()
        self.iface = None
        self.callbacks = {}
        self.recent_events: Dict[str, float] = {}
        self._connect()

    def _connect(self):
        """Attempt to connect to the notification service."""
        if self.iface:
            return True
        try:
            self.iface = self.bus.get(NOTIFY_BUS, NOTIFY_PATH)
            print(f"[NotificationManager] Connected to {NOTIFY_BUS}")
            try:
                self.iface.onActionInvoked = self._on_action
                print(f"[NotificationManager] Registered ActionInvoked callback")
            except Exception as e:
                print(f"[NotificationManager] Failed to register ActionInvoked: {e}")
            return True
        except Exception as e:
            print(f"[NotificationManager] Failed to connect to {NOTIFY_BUS}: {e}")
            self.iface = None
            return False

    def _on_action(self, notif_id: int, action: str):
        print(f"[_on_action] Notification {notif_id} action invoked: {action}")
        # Close the notification when action is clicked
        try:
            self.iface.CloseNotification(notif_id)
            print(f"[_on_action] Closed notification {notif_id}")
        except Exception as e:
            print(f"[_on_action] Failed to close notification {notif_id}: {e}")
        
        cb = self.callbacks.get(notif_id)
        if cb:
            print(f"[_on_action] Calling callback for notification {notif_id}")
            try:
                cb(action)
                print(f"[_on_action] Callback completed successfully")
                # Clean up callback after use
                self.callbacks.pop(notif_id, None)
            except Exception as e:
                print(f"[_on_action] ERROR in callback: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[_on_action] No callback found for notification {notif_id}")

    def _suppress_duplicate(self, devnode: str, action: str, window: float = 1.5) -> bool:
        """
        Drop rapid duplicate notifications for the same device/action to avoid spam from udev churn.
        """
        key = f"{devnode}:{action}"
        now = time.time()
        last = self.recent_events.get(key, 0)
        if now - last < window:
            return True
        self.recent_events[key] = now
        return False

    def notify(self, summary: str, body: str, actions: Optional[Dict[str, Callable[[str], None]]] = None):
        # Retry connection if not connected
        if not self.iface:
            self._connect()
        
        if not self.iface:
            print(f"[notify] {summary}: {body}")
            return
        action_list = []
        action_cb = None
        if actions:
            print(f"[notify] Actions provided: {list(actions.keys())}")
            # Add a "default" action that triggers on notification click
            action_list.extend(["default", ""])
            for key, func in actions.items():
                label = key
                cb = func
                if isinstance(func, tuple):
                    label, cb = func  # type: ignore[assignment]
                action_list.extend([key, label])
                # last callback wins; assuming single action for simplicity
                action_cb = cb
            print(f"[notify] Action list for D-Bus: {action_list}")
        else:
            print(f"[notify] No actions provided")
        
        # Make notification persistent and add urgency
        hints = {
            "urgency": GLib.Variant("y", 2),  # critical urgency
            "resident": GLib.Variant("b", True),  # keep in notification tray
        }
        print(f"[notify] Calling Notify with summary='{summary}', body='{body}', actions={action_list}, hints={hints}")
        notif_id = self.iface.Notify("USB Enforcer", 0, "", summary, body, action_list, hints, 0)
        print(f"[notify] Notification ID returned: {notif_id}")
        if action_cb:
            self.callbacks[notif_id] = action_cb
            print(f"[notify] Registered callback for notification {notif_id}")


def launch_wizard(devnode: str = None):
    import os
    print(f"[launch_wizard] CALLED for device: {devnode}! Starting wizard launch...")
    env = os.environ.copy()
    # Ensure display environment is set
    if "DISPLAY" not in env and "WAYLAND_DISPLAY" not in env:
        print(f"[launch_wizard] Warning: No DISPLAY or WAYLAND_DISPLAY set")
    # Call the bash wrapper script directly (it handles venv/PYTHONPATH internally)
    wizard_script = "/usr/libexec/usb-enforcer-wizard"
    cmd = [wizard_script]
    if devnode:
        cmd.extend(["--device", devnode])
    print(f"[launch_wizard] Command: {' '.join(cmd)}")
    print(f"[launch_wizard] DISPLAY: {env.get('DISPLAY', 'not set')}")
    print(f"[launch_wizard] WAYLAND_DISPLAY: {env.get('WAYLAND_DISPLAY', 'not set')}")
    try:
        # Don't redirect stderr so we can see errors in journal
        proc = subprocess.Popen(cmd, env=env, start_new_session=True)
        print(f"[launch_wizard] Wizard launched with PID {proc.pid}")
    except Exception as e:
        print(f"[launch_wizard] Failed to launch wizard: {e}")
        import traceback
        traceback.print_exc()


def launch_unlock_dialog(devnode: str):
    import os
    print(f"[launch_unlock_dialog] CALLED for {devnode}! Starting unlock dialog...")
    env = os.environ.copy()
    # Call the helper script directly
    helper_script = "/usr/libexec/usb-enforcer-helper"
    cmd = [helper_script, "unlock", devnode]
    print(f"[launch_unlock_dialog] Command: {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(cmd, env=env, start_new_session=True)
        print(f"[launch_unlock_dialog] Unlock dialog launched with PID {proc.pid}")
    except Exception as e:
        print(f"[launch_unlock_dialog] Failed to launch unlock dialog: {e}")
        import traceback
        traceback.print_exc()


def handle_event(fields: Dict[str, str], notifier: NotificationManager) -> None:
    event = fields.get("USB_EE_EVENT", "")
    action = fields.get("ACTION", "")
    devnode = fields.get("DEVNODE", "")
    print(f"[handle_event] event={event} action={action} devnode={devnode}")
    if event == "unlock_prompt" and action == "unlock_prompt":
        # Auto-launch unlock dialog when encrypted device is plugged in
        if notifier._suppress_duplicate(devnode, action):
            print(f"[handle_event] suppressing duplicate unlock prompt for {devnode}")
            return
        print(f"[handle_event] showing unlock notification with action")
        notifier.notify(
            _("Encrypted USB detected"),
            _("Device {device} needs to be unlocked").format(device=devnode),
            actions={"unlock": (_("Unlock drive…"), lambda _a: launch_unlock_dialog(devnode))},
        )
    elif event == "encrypt" and action == "encrypt_done":
        if notifier._suppress_duplicate(devnode, action):
            return
        notifier.notify(_("USB encryption complete"), _("Device {device} mounted writable").format(device=devnode))
    elif event == "encrypt" and action.startswith("encrypt_"):
        # Progress updates visible in wizard UI - no notification spam
        pass
    elif event == "unlock" and action == "unlock_done":
        if notifier._suppress_duplicate(devnode, action):
            return
        notifier.notify(_("Encrypted USB unlocked"), _("Device {device} is now writable").format(device=devnode))
    elif event == "unlock" and action == "unlock_fail":
        if notifier._suppress_duplicate(devnode, action):
            return
        notifier.notify(_("Unlock failed"), _("Device {device} unlock failed").format(device=devnode))
    elif event == "encrypt" and action == "encrypt_fail":
        notifier.notify(_("Encryption failed"), _("Device {device} encryption failed").format(device=devnode))
    elif event == "enforce" and action == "block_rw":
        if notifier._suppress_duplicate(devnode, action):
            print(f"[handle_event] suppressing duplicate for {devnode}:{action}")
            return
        print(f"[handle_event] showing notification with encrypt action for {devnode}")
        notifier.notify(
            _("USB mounted read-only"),
            _("Writing requires encryption."),
            actions={"encrypt": (_("Encrypt drive…"), lambda _a: launch_wizard(devnode))},
        )


def _subscribe_signals(proxy, on_event, on_content_blocked):
    proxy.Event.connect(on_event)
    print("✓ Subscribed to Event signal", flush=True)
    try:
        proxy.ContentBlocked.connect(on_content_blocked)
        print("✓ Subscribed to ContentBlocked signal for content scanning notifications", flush=True)
    except Exception as e:
        print(f"✗ Failed to subscribe to ContentBlocked signal: {e}", flush=True)


def _ensure_proxy(bus, dbus, state, on_event, on_content_blocked):
    try:
        has_owner = dbus.NameHasOwner(BUS_NAME)
    except Exception as e:
        print(f"DBus NameHasOwner check failed: {e}", flush=True)
        has_owner = False

    if not has_owner:
        state["proxy"] = None
        return True

    if state["proxy"] is None:
        try:
            proxy = bus.get(BUS_NAME, BUS_PATH)
            state["proxy"] = proxy
            print("✓ Connected to daemon DBus service", flush=True)
            _subscribe_signals(proxy, on_event, on_content_blocked)
        except Exception as e:
            print(f"Daemon DBus service not available: {e}", flush=True)
    return True


def main():
    bus = pydbus.SystemBus()
    notifier = NotificationManager()
    dbus = bus.get("org.freedesktop.DBus", "/org/freedesktop/DBus")
    state = {"proxy": None}

    def on_event(fields):
        handle_event(fields, notifier)
    
    def on_content_blocked(filepath, reason, patterns, match_count):
        """Handle ContentBlocked signal - show notification when sensitive data is detected"""
        print(f"⛔ Content blocked: {filepath} - {reason}", flush=True)
        notifier.notify(
            _("⛔ File Blocked - Sensitive Data Detected"),
            _("File: {filepath}\n\nReason: {reason}\n\nPatterns detected: {patterns}\n\n{message}").format(
                filepath=filepath,
                reason=reason,
                patterns=patterns,
                message=ngettext(
                    "This file contains {n} sensitive pattern and cannot be written to USB.",
                    "This file contains {n} sensitive patterns and cannot be written to USB.",
                    match_count
                ).format(n=match_count)
            )
        )

    def _poll():
        return _ensure_proxy(bus, dbus, state, on_event, on_content_blocked)

    _poll()
    GLib.timeout_add_seconds(3, _poll)
    print("🎧 USB Enforcer UI listening for events...", flush=True)
    loop = GLib.MainLoop()
    loop.run()


if __name__ == "__main__":
    sys.exit(main() or 0)

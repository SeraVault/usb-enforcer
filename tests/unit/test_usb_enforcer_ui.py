"""Unit tests for usb_enforcer_ui notifications."""

from __future__ import annotations

import importlib
import sys
import types


def _load_ui_module(fake_pydbus=None):
    """Import usb_enforcer_ui with stubbed pydbus/GLib dependencies."""
    if fake_pydbus is None:
        fake_pydbus = types.SimpleNamespace(SystemBus=lambda: None, SessionBus=lambda: None)

    class FakeGLib:
        class Variant:
            def __init__(self, _sig, _val):
                pass

    fake_gi = types.ModuleType("gi")
    fake_gi.require_version = lambda *_args, **_kwargs: None
    fake_repo = types.ModuleType("gi.repository")
    fake_repo.GLib = FakeGLib
    fake_repo.Gio = types.SimpleNamespace()
    fake_repo.Gtk = types.SimpleNamespace()

    sys.modules["pydbus"] = fake_pydbus
    sys.modules["gi"] = fake_gi
    sys.modules["gi.repository"] = fake_repo

    if "usb_enforcer.usb_enforcer_ui" in sys.modules:
        del sys.modules["usb_enforcer.usb_enforcer_ui"]

    return importlib.import_module("usb_enforcer.usb_enforcer_ui")


def test_handle_event_block_rw_triggers_notification():
    ui = _load_ui_module()

    calls = {}

    class DummyNotifier:
        def _suppress_duplicate(self, _devnode, _action):
            return False

        def notify(self, summary, body, actions=None):
            calls["summary"] = summary
            calls["body"] = body
            calls["actions"] = actions or {}

    fields = {
        "USB_EE_EVENT": "enforce",
        "ACTION": "block_rw",
        "DEVNODE": "/dev/sdb1",
    }

    ui.handle_event(fields, DummyNotifier())

    assert calls["summary"] == "USB mounted read-only"
    assert "Writing requires encryption." in calls["body"]
    assert "encrypt" in calls["actions"]


def test_notification_manager_notify_actions_registers_callback():
    calls = {}

    class FakeIface:
        def Notify(self, app_name, replaces_id, app_icon, summary, body, actions, hints, expire_timeout):
            calls["notify"] = {
                "app_name": app_name,
                "summary": summary,
                "body": body,
                "actions": actions,
                "hints": hints,
            }
            return 7

        def CloseNotification(self, notif_id):
            calls["closed"] = notif_id

    class FakeBus:
        def get(self, _bus, _path):
            return FakeIface()

    fake_pydbus = types.SimpleNamespace(SystemBus=lambda: None, SessionBus=lambda: FakeBus())
    ui = _load_ui_module(fake_pydbus=fake_pydbus)

    notifier = ui.NotificationManager()
    notifier.notify("Test", "Body", actions={"action": ("Do", lambda _a: None)})

    assert calls["notify"]["summary"] == "Test"
    assert "default" in calls["notify"]["actions"]
    assert 7 in notifier.callbacks


def test_notification_manager_on_action_closes_and_calls_callback():
    calls = {"cb": 0}

    class FakeIface:
        def CloseNotification(self, notif_id):
            calls["closed"] = notif_id

    ui = _load_ui_module()
    notifier = ui.NotificationManager()
    notifier.iface = FakeIface()
    notifier.callbacks[3] = lambda _a: calls.__setitem__("cb", calls["cb"] + 1)

    notifier._on_action(3, "clicked")

    assert calls["closed"] == 3
    assert calls["cb"] == 1
    assert 3 not in notifier.callbacks


def test_suppress_duplicate_window():
    ui = _load_ui_module()
    notifier = ui.NotificationManager()

    times = [100.0, 100.5, 102.0]
    ui.time.time = lambda: times.pop(0)

    assert notifier._suppress_duplicate("/dev/sdb1", "block_rw") is False
    assert notifier._suppress_duplicate("/dev/sdb1", "block_rw") is True
    assert notifier._suppress_duplicate("/dev/sdb1", "block_rw") is False


def test_ensure_proxy_subscribes_when_owner_present():
    ui = _load_ui_module()
    state = {"proxy": None}
    calls = {"event": 0, "blocked": 0}

    class FakeSignal:
        def __init__(self, key):
            self.key = key

        def connect(self, _cb):
            calls[self.key] += 1

    class FakeProxy:
        Event = FakeSignal("event")
        ContentBlocked = FakeSignal("blocked")

    class FakeBus:
        def get(self, _bus, _path):
            return FakeProxy()

    class FakeDBus:
        def NameHasOwner(self, _name):
            return True

    def on_event(_fields):
        pass

    def on_content_blocked(_filepath, _reason, _patterns, _match_count):
        pass

    ui._ensure_proxy(FakeBus(), FakeDBus(), state, on_event, on_content_blocked)

    assert state["proxy"] is not None
    assert calls["event"] == 1
    assert calls["blocked"] == 1


def test_ensure_proxy_clears_proxy_when_owner_missing():
    ui = _load_ui_module()
    state = {"proxy": object()}

    class FakeDBus:
        def NameHasOwner(self, _name):
            return False

    ui._ensure_proxy(object(), FakeDBus(), state, lambda _f: None, lambda *_a: None)

    assert state["proxy"] is None

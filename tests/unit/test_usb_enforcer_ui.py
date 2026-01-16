"""Unit tests for usb_enforcer_ui notifications."""

from __future__ import annotations

import importlib
import sys
import types


def _load_ui_module():
    """Import usb_enforcer_ui with stubbed pydbus/GLib dependencies."""
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

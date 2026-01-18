"""Unit tests for content scanning notification helpers."""

from __future__ import annotations

import importlib
import sys
import types


def _load_notifications_module():
    fake_gi = types.ModuleType("gi")
    fake_gi.require_version = lambda *_args, **_kwargs: None

    class FakeNotification:
        def __init__(self, title):
            self.title = title
            self.body = ""
            self.priority = None

        @classmethod
        def new(cls, title):
            return cls(title)

        def set_body(self, body):
            self.body = body

        def set_priority(self, priority):
            self.priority = priority

    class FakeGio:
        Notification = FakeNotification

        class NotificationPriority:
            URGENT = "urgent"

        class Application:
            @staticmethod
            def get_default():
                return None

    class FakeGLib:
        @staticmethod
        def idle_add(func, *args):
            return func(*args)

    class FakeGtk:
        Application = object
        ApplicationWindow = object
        Orientation = types.SimpleNamespace(VERTICAL=1)
        Align = types.SimpleNamespace(START=1)

    fake_repo = types.ModuleType("gi.repository")
    fake_repo.GLib = FakeGLib
    fake_repo.Gio = FakeGio
    fake_repo.Gtk = FakeGtk
    fake_repo.Adw = types.SimpleNamespace()

    sys.modules["gi"] = fake_gi
    sys.modules["gi.repository"] = fake_repo

    if "usb_enforcer.content_verification.notifications" in sys.modules:
        del sys.modules["usb_enforcer.content_verification.notifications"]

    return importlib.import_module("usb_enforcer.content_verification.notifications")


def test_notify_scan_progress_uses_idle_add():
    notifications = _load_notifications_module()

    calls = {}

    class DummyNotifier:
        def show_scan_progress(self, filepath, progress, status, total_size, scanned_size):
            calls["args"] = (filepath, progress, status, total_size, scanned_size)

    service = notifications.ScanNotificationService(DummyNotifier())
    service.notify_scan_progress("/tmp/test.txt", 10.0, "scanning", 100, 10)

    assert calls["args"][0] == "/tmp/test.txt"
    assert calls["args"][2] == "scanning"


def test_notify_blocked_sends_notification():
    notifications = _load_notifications_module()

    calls = {}

    class FakeApp:
        def send_notification(self, notif_id, notification):
            calls["notif_id"] = notif_id
            calls["notification"] = notification

    notifications.Gio.Application.get_default = staticmethod(lambda: FakeApp())
    service = notifications.ScanNotificationService(notifications.ScanProgressNotifier(object()))

    service.notify_blocked("/tmp/secret.txt", "blocked", "ssn", match_count=2)

    assert calls["notif_id"] == "blocked-file"
    assert "This file was prevented" in calls["notification"].body

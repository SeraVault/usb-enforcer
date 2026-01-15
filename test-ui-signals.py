#!/usr/bin/env python3
"""Test script to verify ContentBlocked signal reception"""
import sys
sys.path.insert(0, '/usr/lib/usb-enforcer')

import pydbus
from gi.repository import GLib

BUS_NAME = "org.seravault.UsbEnforcer"
BUS_PATH = "/org/seravault/UsbEnforcer"

def on_content_blocked(filepath, reason, patterns, match_count):
    print(f"⛔ RECEIVED ContentBlocked signal!")
    print(f"   Filepath: {filepath}")
    print(f"   Reason: {reason}")
    print(f"   Patterns: {patterns}")
    print(f"   Match count: {match_count}")
    sys.stdout.flush()

try:
    bus = pydbus.SystemBus()
    proxy = bus.get(BUS_NAME, BUS_PATH)
    print(f"✓ Connected to {BUS_NAME}")
    
    proxy.ContentBlocked.connect(on_content_blocked)
    print(f"✓ Subscribed to ContentBlocked signal")
    print("Waiting for signals... (copy test-ssn.txt to USB now)")
    sys.stdout.flush()
    
    loop = GLib.MainLoop()
    loop.run()
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()

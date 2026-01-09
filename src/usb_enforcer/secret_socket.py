from __future__ import annotations

import json
import os
import socket
from typing import Optional


SOCKET_PATH = os.environ.get("USB_EE_SOCKET", "/run/usb-encryption-enforcer.sock")


class SecretSocketError(Exception):
    pass


def send_secret(op: str, devnode: str, passphrase: str, mapper: Optional[str] = None, token: Optional[str] = None, timeout: float = 5.0) -> str:
    """
    Send passphrase over a local UNIX socket, get back a one-time token.
    """
    payload = {"op": op, "devnode": devnode, "passphrase": passphrase}
    if mapper:
        payload["mapper"] = mapper
    if token:
        payload["token"] = token

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(SOCKET_PATH)
        sock.sendall(json.dumps(payload).encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)
        data = sock.recv(4096)
    except Exception as exc:
        raise SecretSocketError(f"secret socket error: {exc}") from exc
    finally:
        try:
            sock.close()
        except Exception:
            pass

    try:
        resp = json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise SecretSocketError(f"invalid response: {exc}") from exc
    if resp.get("status") != "ok":
        raise SecretSocketError(resp.get("error", "secret socket error"))
    token_val = resp.get("token")
    if not token_val:
        raise SecretSocketError("no token returned")
    return token_val

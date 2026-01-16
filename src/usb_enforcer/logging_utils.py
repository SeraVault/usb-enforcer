from __future__ import annotations

import logging
from typing import Any, Dict

try:
    from systemd.journal import JournalHandler
except Exception:  # pragma: no cover
    JournalHandler = None


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("usb_encryption_enforcer")
    logger.setLevel(level)
    if not logger.handlers:
        if JournalHandler:
            handler = JournalHandler()
        else:
            handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


def log_structured(logger: logging.Logger, message: str, extra_fields: Dict[str, Any]) -> None:
    # systemd.journal.JournalHandler accepts dict in extra; fallback to plain logging otherwise.
    handlers = getattr(logger, "handlers", [])
    try:
        iter(handlers)
    except TypeError:
        handlers = []
    if JournalHandler and any(isinstance(h, JournalHandler) for h in handlers):
        logger.info(message, extra=extra_fields)
        return
    if extra_fields:
        fields = " ".join(f"{key}={value}" for key, value in extra_fields.items())
        logger.info(f"{message} {fields}")
        return
    logger.info(message)

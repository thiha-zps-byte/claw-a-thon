"""Minimal structured logging.

Emits single-line key=value records. Never logs secrets or full message bodies —
callers pass only non-sensitive fields (request id, latency, model, token counts).
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)


def kv(**fields: object) -> str:
    """Render structured fields as a compact key=value string."""
    return " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)

"""Minimal structured logging.

Emits single-line key=value records. Never logs secrets or full message bodies —
callers pass only non-sensitive fields (request id, latency, model, token counts).
"""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler

# A real log line starts with "YYYY-MM-DD HH:MM:SS[,ms] LEVEL logger message".
_HEADER_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d[,.\d]*) (\w+) (\S+) (.*)$")

_CONFIGURED = False
_LOG_FILE = None  # resolved path of the on-disk log, for recent_logs()
_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _log_file_path():
    """<LOG_DIR or data_dir/logs>/app.log; None if it can't be resolved."""
    try:
        from app.config import get_settings

        d = get_settings(require_secrets=False).log_dir
        d.mkdir(parents=True, exist_ok=True)
        return d / "app.log"
    except Exception:  # noqa: BLE001 — logging must never crash the app
        return None


def setup_logging(level: str = "INFO") -> None:
    global _CONFIGURED, _LOG_FILE
    if _CONFIGURED:
        return
    fmt = logging.Formatter(_FORMAT)
    root = logging.getLogger()
    root.setLevel(level)

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    root.addHandler(stream)

    # Persist to disk so logs are viewable in-app (and survive a mounted volume).
    path = _log_file_path()
    if path is not None:
        try:
            fileh = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
            fileh.setFormatter(fmt)
            root.addHandler(fileh)
            _LOG_FILE = path
        except Exception:  # noqa: BLE001
            pass
    _CONFIGURED = True


def recent_logs(level: str | None = None, limit: int = 200) -> list[dict]:
    """Read the tail of the on-disk log file as structured records (newest first)."""
    if _LOG_FILE is None or not _LOG_FILE.exists():
        return []
    try:
        lines = _LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    # Parse forward, folding continuation lines (tracebacks) into the prior record.
    records: list[dict] = []
    for line in lines:
        m = _HEADER_RE.match(line)
        if m:
            records.append({"time": m.group(1), "level": m.group(2),
                            "logger": m.group(3), "message": m.group(4)})
        elif records:
            records[-1]["message"] += "\n" + line
    if level:
        records = [r for r in records if r["level"] == level.upper()]
    return list(reversed(records))[:limit]


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)


def kv(**fields: object) -> str:
    """Render structured fields as a compact key=value string."""
    return " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)

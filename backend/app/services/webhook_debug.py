"""On-disk debug feed of inbound webhook events (for the admin debug panel).

Each event is one JSON line in ``<LOG_DIR>/webhook.jsonl``. Best-effort: failures are
swallowed so debugging never affects request handling. The file is trimmed to keep it
small. Note: container disk is ephemeral unless a volume is mounted.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.config import get_settings
from app.core.logging import get_logger

log = get_logger("webhook_debug")

_MAX_LINES = 1000
_MAX_PAYLOAD = 8000


def _path():
    d = get_settings(require_secrets=False).log_dir
    d.mkdir(parents=True, exist_ok=True)
    return d / "webhook.jsonl"


def record(entry: dict) -> None:
    """Append one webhook event (adds a timestamp; truncates oversized payloads)."""
    try:
        entry = {"time": datetime.now(UTC).isoformat(), **entry}
        payload = entry.get("payload")
        if payload is not None:
            blob = json.dumps(payload, ensure_ascii=False)
            if len(blob) > _MAX_PAYLOAD:
                entry["payload"] = {"_truncated": blob[:_MAX_PAYLOAD]}
        path = _path()
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _trim(path)
    except Exception:  # noqa: BLE001 — debug logging must never break the webhook
        log.warning("webhook_debug record failed")


def _trim(path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MAX_LINES:
            path.write_text("\n".join(lines[-_MAX_LINES:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def recent(page_id: str | None = None, limit: int = 50) -> list[dict]:
    """Most-recent-first events, optionally filtered by Page id."""
    try:
        path = _path()
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if page_id and e.get("page_id") != page_id:
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return out

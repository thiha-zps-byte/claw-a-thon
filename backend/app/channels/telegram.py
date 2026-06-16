"""Telegram outbound adapter (Bot API).

One-way escalation: forward "hard cases" into a support group. ``send_message`` never
raises (forwarding is best-effort and must not break a chat reply); ``get_me`` returns
a structured result for the "test connection" UI affordance.
"""

from __future__ import annotations

import httpx

from app.core.logging import get_logger

log = get_logger("telegram")

_API_BASE = "https://api.telegram.org"
_TIMEOUT = 15.0


async def send_message(bot_token: str, chat_id: str, text: str, parse_mode: str = "") -> bool:
    """Send a text message to a chat/group id. Returns True on success (never raises).

    ``parse_mode`` (e.g. "HTML") enables rich formatting; omit for plain text.
    """
    if not bot_token or not chat_id:
        return False
    payload: dict = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(f"{_API_BASE}/bot{bot_token}/sendMessage", json=payload)
        if resp.status_code == 200 and resp.json().get("ok"):
            return True
        log.warning("telegram send failed: status=%s body=%s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:  # noqa: BLE001
        log.warning("telegram send error: %s", type(exc).__name__)
        return False


async def get_me(bot_token: str) -> dict:
    """Validate a bot token via getMe. Returns {ok, username?, error?}."""
    if not bot_token:
        return {"ok": False, "error": "Thiếu bot token."}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_API_BASE}/bot{bot_token}/getMe")
        data = resp.json()
        if resp.status_code == 200 and data.get("ok"):
            return {"ok": True, "username": data["result"].get("username", "")}
        return {"ok": False, "error": data.get("description", "Token không hợp lệ.")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"Lỗi kết nối Telegram ({type(exc).__name__})."}

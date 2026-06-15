"""Facebook Messenger outbound adapter (Graph API).

Sends replies and typing indicators for a Page, and validates a Page id + token
pair so the operator can confirm credentials before connecting a real Page.

Send helpers never raise: webhook delivery is fire-and-forget, so a failed send is
logged, not propagated. ``validate_credentials`` returns a structured result instead
of raising, because it drives a UI affordance.
"""

from __future__ import annotations

import httpx

from app.core.logging import get_logger

log = get_logger("messenger")

# Pin a recent stable Graph API version; bump as Meta deprecates older ones.
GRAPH_VERSION = "v19.0"
_GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
_TIMEOUT = 15.0

# Events we ask the Page to deliver to the app's webhook.
_SUBSCRIBED_FIELDS = "messages,messaging_postbacks"


async def send_text(page_token: str, recipient_psid: str, text: str) -> bool:
    """Send a text message to a PSID. Returns True on success (never raises)."""
    payload = {
        "recipient": {"id": recipient_psid},
        "messaging_type": "RESPONSE",
        "message": {"text": text},
    }
    return await _post_message(page_token, payload, what="text")


async def send_typing(page_token: str, recipient_psid: str) -> bool:
    """Show the 'typing…' indicator to a PSID. Returns True on success."""
    payload = {"recipient": {"id": recipient_psid}, "sender_action": "typing_on"}
    return await _post_message(page_token, payload, what="typing")


async def _post_message(page_token: str, payload: dict, *, what: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_GRAPH_BASE}/me/messages",
                params={"access_token": page_token},
                json=payload,
            )
        if resp.status_code >= 400:
            log.warning("messenger send_%s failed: HTTP %s %s", what, resp.status_code, resp.text[:300])
            return False
        return True
    except Exception as exc:  # noqa: BLE001 — delivery is best-effort
        log.warning("messenger send_%s error: %s", what, type(exc).__name__)
        return False


async def subscribe_page(page_token: str) -> dict:
    """Subscribe the app to the Page's message events (so it receives webhooks).

    Uses the Page Access Token alone (``POST /me/subscribed_apps``), so the operator
    skips the manual "subscribe page" step in the Meta dashboard. Returns
    ``{"ok": bool, "error"?: str}``.
    """
    if not page_token:
        return {"ok": False, "error": "Chưa có Page Access Token để đăng ký."}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_GRAPH_BASE}/me/subscribed_apps",
                params={"subscribed_fields": _SUBSCRIBED_FIELDS, "access_token": page_token},
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("messenger subscribe error: %s", type(exc).__name__)
        return {"ok": False, "error": "Không kết nối được tới Facebook. Vui lòng thử lại."}

    if resp.status_code >= 400:
        log.warning("messenger subscribe failed: HTTP %s %s", resp.status_code, resp.text[:300])
        return {"ok": False, "error": "Đăng ký Page thất bại. Kiểm tra lại Page Access Token."}
    if not resp.json().get("success", False):
        return {"ok": False, "error": "Facebook không xác nhận đăng ký. Thử lại sau."}
    return {"ok": True}


async def validate_credentials(page_token: str, expected_page_id: str) -> dict:
    """Verify that ``page_token`` is valid and belongs to ``expected_page_id``.

    Returns ``{"ok": bool, "page_name"?: str, "page_id"?: str, "error"?: str}``.
    Calls ``GET /me`` with the Page token, which resolves to the Page object.
    """
    if not page_token:
        return {"ok": False, "error": "Chưa có Page Access Token để kiểm tra."}
    if not expected_page_id:
        return {"ok": False, "error": "Chưa nhập Page ID để đối chiếu."}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_GRAPH_BASE}/me",
                params={"fields": "id,name", "access_token": page_token},
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("messenger validate error: %s", type(exc).__name__)
        return {"ok": False, "error": "Không kết nối được tới Facebook. Vui lòng thử lại."}

    if resp.status_code >= 400:
        return {"ok": False, "error": "Page Access Token không hợp lệ hoặc đã hết hạn."}

    data = resp.json()
    actual_id = str(data.get("id") or "")
    if actual_id != str(expected_page_id):
        return {
            "ok": False,
            "page_id": actual_id,
            "error": (
                "Token hợp lệ nhưng thuộc Page khác "
                f"(id «{actual_id}»). Hãy kiểm tra lại Page ID."
            ),
        }
    return {"ok": True, "page_id": actual_id, "page_name": data.get("name") or ""}

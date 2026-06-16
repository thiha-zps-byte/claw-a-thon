"""Webhook debug feed + on-disk raw log viewer (admin/owner)."""

from __future__ import annotations

import hashlib
import hmac
import json

H = {"X-UID": "owner-1"}
PAGE_ID = "PAGE1"
APP_SECRET = "s3cret"


def _make_bot(client) -> str:
    bot_id = client.post("/api/bots", json={"name": "FB Bot"}, headers=H).json()["bot"]["id"]
    client.patch(
        f"/api/bots/{bot_id}",
        json={
            "messenger_enabled": True,
            "messenger_page_id": PAGE_ID,
            "messenger_page_token": "ptok",
            "messenger_app_secret": APP_SECRET,
        },
        headers=H,
    )
    return bot_id


def _mock_turn(monkeypatch):
    from app.services.agent_service import TurnResult, agent_service

    async def fake(bot, documents, message, uid, session_id):
        return TurnResult(reply="ok", category="other", delay=0.1)

    monkeypatch.setattr(agent_service, "run_turn", fake)


def _mute_sends(monkeypatch):
    async def ok(*a, **k):
        return True

    monkeypatch.setattr("app.channels.messenger.send_text", ok)
    monkeypatch.setattr("app.channels.messenger.send_typing", ok)


def _dm(page_id, text="xin chào"):
    return {"object": "page", "entry": [{"id": page_id, "messaging": [
        {"sender": {"id": "PSID1"}, "message": {"text": text}}]}]}


def _post(client, body, *, sign=True):
    raw = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if sign:
        headers["X-Hub-Signature-256"] = "sha256=" + hmac.new(
            APP_SECRET.encode(), raw, hashlib.sha256
        ).hexdigest()
    else:
        headers["X-Hub-Signature-256"] = "sha256=deadbeef"
    return client.post("/api/webhooks/messenger", content=raw, headers=headers)


def test_valid_event_recorded(client, monkeypatch):
    _mock_turn(monkeypatch)
    _mute_sends(monkeypatch)
    bot_id = _make_bot(client)
    _post(client, _dm(PAGE_ID, "câu hỏi A"))

    r = client.get(f"/api/bots/{bot_id}/webhook/debug", headers=H)
    assert r.status_code == 200
    events = r.json()["events"]
    assert len(events) >= 1
    assert events[0]["signature_valid"] is True
    assert events[0]["page_id"] == PAGE_ID
    assert "câu hỏi A" in json.dumps(events[0]["payload"], ensure_ascii=False)


def test_bad_signature_recorded(client, monkeypatch):
    _mock_turn(monkeypatch)
    _mute_sends(monkeypatch)
    bot_id = _make_bot(client)
    _post(client, _dm(PAGE_ID), sign=False)

    events = client.get(f"/api/bots/{bot_id}/webhook/debug", headers=H).json()["events"]
    assert any(e["signature_valid"] is False for e in events)


def test_debug_endpoint_owner_scoped(client):
    bot_id = _make_bot(client)
    assert client.get(
        f"/api/bots/{bot_id}/webhook/debug", headers={"X-UID": "intruder"}
    ).status_code == 404


def test_recent_filters_by_page():
    from app.services import webhook_debug

    webhook_debug.record({"kind": "event", "page_id": "PX", "payload": {"a": 1}})
    webhook_debug.record({"kind": "event", "page_id": "PY", "payload": {"b": 2}})
    px = webhook_debug.recent("PX", limit=50)
    assert px and all(e["page_id"] == "PX" for e in px)


def test_logs_written_to_disk_and_admin_only(client):
    from app.core.logging import get_logger, recent_logs

    get_logger("test_dbg").warning("hello debug marker xyz")
    logs = recent_logs(limit=200)
    assert any("xyz" in r["message"] for r in logs)

    # admin can read; a normal user cannot.
    assert client.get("/api/debug/logs", headers={"X-UID": "admin"}).status_code == 200
    assert client.get("/api/debug/logs", headers={"X-UID": "owner-1"}).status_code == 404

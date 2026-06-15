"""Facebook Messenger channel: write-only secrets, webhook, simulate, validate.

All Facebook/LLM I/O is mocked — these prove the routing, signature, and write-only
secret logic without any network access (Lớp 3 of the test strategy).
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

H = {"X-UID": "owner-1"}


def _make_bot(client, **messenger) -> str:
    bot_id = client.post("/api/bots", json={"name": "FB Bot"}, headers=H).json()["bot"]["id"]
    if messenger:
        client.patch(f"/api/bots/{bot_id}", json=messenger, headers=H)
    return bot_id


def _mock_turn(monkeypatch):
    from app.services.agent_service import TurnResult, agent_service

    async def fake_turn(bot, documents, message, uid, session_id):
        return TurnResult(reply=f"echo: {message}", category="other", delay=0.5)

    monkeypatch.setattr(agent_service, "run_turn", fake_turn)


def _record_sends(monkeypatch) -> dict:
    calls: dict = {"text": [], "typing": []}

    async def fake_send_text(page_token, psid, text):
        calls["text"].append((page_token, psid, text))
        return True

    async def fake_send_typing(page_token, psid):
        calls["typing"].append((page_token, psid))
        return True

    monkeypatch.setattr("app.channels.messenger.send_text", fake_send_text)
    monkeypatch.setattr("app.channels.messenger.send_typing", fake_send_typing)
    return calls


# --- write-only secrets -------------------------------------------------------


def test_secrets_are_write_only_in_responses(client):
    bot_id = _make_bot(
        client,
        messenger_enabled=True,
        messenger_page_id="PAGE1",
        messenger_verify_token="vtok",
        messenger_page_token="ptok-secret",
        messenger_app_secret="appsecret",
    )
    bot = client.get(f"/api/bots/{bot_id}", headers=H).json()["bot"]
    # Non-secret fields round-trip…
    assert bot["messenger_enabled"] is True
    assert bot["messenger_page_id"] == "PAGE1"
    assert bot["messenger_verify_token"] == "vtok"
    # …secrets are exposed only as booleans, never raw values.
    assert bot["messenger_page_token_set"] is True
    assert bot["messenger_app_secret_set"] is True
    assert "messenger_page_token" not in bot
    assert "messenger_app_secret" not in bot


def test_blank_secret_keeps_stored_value(client):
    bot_id = _make_bot(
        client,
        messenger_page_id="PAGE1",
        messenger_page_token="ptok-secret",
    )
    # PATCH other fields with blank token → stored secret must be kept.
    client.patch(
        f"/api/bots/{bot_id}",
        json={"messenger_page_id": "PAGE2", "messenger_page_token": ""},
        headers=H,
    )
    from app.db.database import get_session
    from app.db.repository import BotRepository

    with get_session() as session:
        bot = BotRepository(session).get(bot_id)
        assert bot.messenger_page_id == "PAGE2"
        assert bot.messenger_page_token == "ptok-secret"  # unchanged

    # A non-empty value replaces it.
    client.patch(f"/api/bots/{bot_id}", json={"messenger_page_token": "new-tok"}, headers=H)
    with get_session() as session:
        assert BotRepository(session).get(bot_id).messenger_page_token == "new-tok"


# --- simulate (dry-run) -------------------------------------------------------


def test_simulate_returns_reply_without_sending(client, monkeypatch):
    _mock_turn(monkeypatch)
    calls = _record_sends(monkeypatch)
    bot_id = _make_bot(client, messenger_page_id="PAGE1")

    r = client.post(
        f"/api/bots/{bot_id}/messenger/simulate", json={"message": "nạp thẻ sao"}, headers=H
    )
    assert r.status_code == 200
    assert r.json()["reply"] == "echo: nạp thẻ sao"
    # Dry-run: no Facebook delivery.
    assert calls["text"] == []
    assert calls["typing"] == []


def test_simulate_requires_ownership(client, monkeypatch):
    _mock_turn(monkeypatch)
    bot_id = _make_bot(client)
    r = client.post(
        f"/api/bots/{bot_id}/messenger/simulate",
        json={"message": "hi"},
        headers={"X-UID": "intruder"},
    )
    assert r.status_code == 404


# --- webhook GET handshake ----------------------------------------------------


def test_webhook_verify_handshake(client):
    _make_bot(client, messenger_enabled=True, messenger_verify_token="vtok")
    r = client.get(
        "/api/webhooks/messenger",
        params={"hub.mode": "subscribe", "hub.verify_token": "vtok", "hub.challenge": "98765"},
    )
    assert r.status_code == 200
    assert r.text == "98765"


def test_webhook_verify_rejects_wrong_token(client):
    _make_bot(client, messenger_enabled=True, messenger_verify_token="vtok")
    r = client.get(
        "/api/webhooks/messenger",
        params={"hub.mode": "subscribe", "hub.verify_token": "WRONG", "hub.challenge": "x"},
    )
    assert r.status_code == 403


# --- webhook POST events ------------------------------------------------------


def _signed_post(client, body: dict, app_secret: str | None):
    raw = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if app_secret is not None:
        sig = hmac.new(app_secret.encode(), raw, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = "sha256=" + sig
    return client.post("/api/webhooks/messenger", content=raw, headers=headers)


def _page_event(page_id: str, psid: str, text: str) -> dict:
    return {
        "object": "page",
        "entry": [{"id": page_id, "messaging": [{"sender": {"id": psid}, "message": {"text": text}}]}],
    }


def test_webhook_routes_and_replies(client, monkeypatch):
    _mock_turn(monkeypatch)
    calls = _record_sends(monkeypatch)
    _make_bot(
        client,
        messenger_enabled=True,
        messenger_page_id="PAGE1",
        messenger_page_token="ptok",
        messenger_app_secret="s3cret",
    )

    r = _signed_post(client, _page_event("PAGE1", "PSID1", "xin chào"), app_secret="s3cret")
    assert r.status_code == 200
    # Background task runs within the TestClient request cycle.
    assert calls["text"] == [("ptok", "PSID1", "echo: xin chào")]
    assert calls["typing"] == [("ptok", "PSID1")]


def test_webhook_rejects_bad_signature(client, monkeypatch):
    _mock_turn(monkeypatch)
    calls = _record_sends(monkeypatch)
    _make_bot(
        client,
        messenger_enabled=True,
        messenger_page_id="PAGE1",
        messenger_page_token="ptok",
        messenger_app_secret="s3cret",
    )

    raw = json.dumps(_page_event("PAGE1", "PSID1", "hi")).encode()
    r = client.post(
        "/api/webhooks/messenger",
        content=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert r.status_code == 200  # still 200 so FB stops retrying
    assert calls["text"] == []  # but nothing delivered


def test_webhook_unknown_page_is_ignored(client, monkeypatch):
    _mock_turn(monkeypatch)
    calls = _record_sends(monkeypatch)
    _make_bot(client, messenger_enabled=True, messenger_page_id="PAGE1", messenger_app_secret="s")
    r = _signed_post(client, _page_event("OTHER", "PSID1", "hi"), app_secret="s")
    assert r.status_code == 200
    assert calls["text"] == []


# --- validate endpoint --------------------------------------------------------


def test_validate_calls_graph_and_returns_result(client, monkeypatch):
    seen: dict = {}

    async def fake_validate(page_token, page_id):
        seen["args"] = (page_token, page_id)
        return {"ok": True, "page_name": "ZingSpeed Fanpage", "page_id": page_id}

    monkeypatch.setattr("app.channels.messenger.validate_credentials", fake_validate)
    bot_id = _make_bot(client, messenger_page_id="PAGE1", messenger_page_token="stored-tok")

    # Blank token in body → falls back to the stored one.
    r = client.post(
        f"/api/bots/{bot_id}/messenger/validate", json={"page_id": "PAGE1"}, headers=H
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert seen["args"] == ("stored-tok", "PAGE1")


# --- subscribe endpoint -------------------------------------------------------


def test_subscribe_uses_stored_token(client, monkeypatch):
    seen: dict = {}

    async def fake_subscribe(page_token):
        seen["token"] = page_token
        return {"ok": True}

    monkeypatch.setattr("app.channels.messenger.subscribe_page", fake_subscribe)
    bot_id = _make_bot(client, messenger_page_id="PAGE1", messenger_page_token="stored-tok")

    r = client.post(f"/api/bots/{bot_id}/messenger/subscribe", json={}, headers=H)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert seen["token"] == "stored-tok"


# --- migration ----------------------------------------------------------------


def test_migrate_bot_columns_is_idempotent():
    from sqlmodel import create_engine

    from app.db.database import _BOT_ADDED_COLUMNS, _migrate_bot_columns

    engine = create_engine("sqlite://")  # in-memory
    with engine.begin() as conn:
        # Pre-Messenger schema: bots without the new columns.
        conn.exec_driver_sql("CREATE TABLE bots (id VARCHAR PRIMARY KEY, name VARCHAR)")

    _migrate_bot_columns(engine)
    _migrate_bot_columns(engine)  # second run must be a no-op, not an error

    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(bots)")}
    assert set(_BOT_ADDED_COLUMNS).issubset(cols)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

"""Facebook Page comment handling: a comment on a post → bot DMs the commenter.

Webhook ``feed`` events are routed by Page id, the bot answers via the shared chat
pipeline, and the reply is sent as a Messenger private reply. All FB/LLM I/O mocked.
"""

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

    async def fake_turn(bot, documents, message, uid, session_id):
        return TurnResult(reply=f"echo: {message}", category="other", delay=0.1)

    monkeypatch.setattr(agent_service, "run_turn", fake_turn)


def _record_private(monkeypatch) -> list:
    calls: list = []

    async def fake(page_token, comment_id, text):
        calls.append((page_token, comment_id, text))
        return True

    monkeypatch.setattr("app.channels.messenger.private_reply", fake)
    return calls


def _feed(page_id, *, comment_id="c1", from_id="USER1", text="cho mình xin thông tin",
          verb="add", item="comment"):
    return {
        "object": "page",
        "entry": [{
            "id": page_id,
            "changes": [{
                "field": "feed",
                "value": {
                    "item": item,
                    "verb": verb,
                    "comment_id": comment_id,
                    "post_id": f"{page_id}_post",
                    "from": {"id": from_id, "name": "Người chơi"},
                    "message": text,
                },
            }],
        }],
    }


def _signed_post(client, body, app_secret=APP_SECRET):
    raw = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if app_secret is not None:
        sig = hmac.new(app_secret.encode(), raw, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = "sha256=" + sig
    return client.post("/api/webhooks/messenger", content=raw, headers=headers)


def test_comment_triggers_private_reply(client, monkeypatch):
    _mock_turn(monkeypatch)
    calls = _record_private(monkeypatch)
    bot_id = _make_bot(client)

    r = _signed_post(client, _feed(PAGE_ID, comment_id="cmt-9", text="cho mình xin code"))
    assert r.status_code == 200
    assert calls == [("ptok", "cmt-9", "echo: cho mình xin code")]

    from app.db.database import get_session
    from app.db.repository import MessageEventRepository

    with get_session() as s:
        events = MessageEventRepository(s).events_since(bot_id, None)
    assert len(events) == 1


def test_skips_page_own_comment(client, monkeypatch):
    _mock_turn(monkeypatch)
    calls = _record_private(monkeypatch)
    _make_bot(client)
    # A comment authored by the Page itself must NOT be answered (avoids a loop).
    _signed_post(client, _feed(PAGE_ID, from_id=PAGE_ID))
    assert calls == []


def test_skips_non_add_and_non_comment(client, monkeypatch):
    _mock_turn(monkeypatch)
    calls = _record_private(monkeypatch)
    _make_bot(client)
    _signed_post(client, _feed(PAGE_ID, verb="edited"))
    _signed_post(client, _feed(PAGE_ID, item="status"))
    _signed_post(client, _feed(PAGE_ID, text=""))
    assert calls == []


def test_bad_signature_skips(client, monkeypatch):
    _mock_turn(monkeypatch)
    calls = _record_private(monkeypatch)
    _make_bot(client)
    raw = json.dumps(_feed(PAGE_ID)).encode()
    r = client.post(
        "/api/webhooks/messenger",
        content=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert r.status_code == 200
    assert calls == []


def test_feed_is_subscribed():
    from app.channels import messenger

    assert "feed" in messenger._SUBSCRIBED_FIELDS

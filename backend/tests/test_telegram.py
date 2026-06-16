"""Telegram escalation: forward 'hard cases' to a support group (one-way).

LLM/Telegram I/O is mocked. Proves the forward trigger (degraded OR needs_human),
write-only token, the escalated stat, and the owner-scoped test endpoint.
"""

from __future__ import annotations

H = {"X-UID": "owner-1"}


def _mock_turn(monkeypatch, *, degraded=False, needs_human=False, category="ontopic"):
    from app.services.agent_service import TurnResult, agent_service

    async def fake(bot, documents, message, uid, session_id):
        return TurnResult(
            reply="(fallback)" if degraded else f"reply: {message}",
            category=category,
            delay=0.1,
            degraded=degraded,
            needs_human=needs_human,
        )

    monkeypatch.setattr(agent_service, "run_turn", fake)


def _record_sends(monkeypatch) -> list:
    calls: list = []

    async def fake_send(token, chat_id, text, parse_mode=""):
        calls.append((token, chat_id, text))
        return True

    monkeypatch.setattr("app.channels.telegram.send_message", fake_send)
    return calls


def _mock_summary(monkeypatch):
    # Avoid a real LLM call for the ticket summary; echo the message for assertions.
    monkeypatch.setattr("app.agents.behavior.escalation.summarize", lambda m: f"tóm tắt: {m}")


def _make_bot(client, **fields) -> str:
    bot_id = client.post("/api/bots", json={"name": "TG Bot"}, headers=H).json()["bot"]["id"]
    base = {
        "telegram_forward_enabled": True,
        "telegram_bot_token": "tg-tok",
        "telegram_group_id": "-999",
    }
    base.update(fields)
    client.patch(f"/api/bots/{bot_id}", json=base, headers=H)
    return bot_id


def _events(bot_id):
    from app.db.database import get_session
    from app.db.repository import MessageEventRepository

    with get_session() as s:
        evs = MessageEventRepository(s).events_since(bot_id, None)
        s.expunge_all()
    return evs


# --- forward trigger ----------------------------------------------------------


def test_degraded_forwards_to_group(client, monkeypatch):
    _mock_turn(monkeypatch, degraded=True)
    _mock_summary(monkeypatch)
    calls = _record_sends(monkeypatch)
    bot_id = _make_bot(client)

    r = client.post("/api/chat", json={"bot_id": bot_id, "message": "câu rất khó"}, headers=H)
    assert r.status_code == 200
    assert len(calls) == 1
    token, chat_id, text = calls[0]
    assert token == "tg-tok" and chat_id == "-999"
    assert "<pre>" in text             # Telegram code-block format
    assert "[TICKET]" in text          # ticket format
    assert "câu rất khó" in text       # summary carries the issue
    assert _events(bot_id)[0].escalated is True


def test_needs_human_forwards(client, monkeypatch):
    _mock_turn(monkeypatch, needs_human=True)
    _mock_summary(monkeypatch)
    calls = _record_sends(monkeypatch)
    bot_id = _make_bot(client)
    client.post("/api/chat", json={"bot_id": bot_id, "message": "mình bị trừ tiền"}, headers=H)
    assert len(calls) == 1


def test_normal_answer_does_not_forward(client, monkeypatch):
    _mock_turn(monkeypatch, degraded=False, needs_human=False)
    calls = _record_sends(monkeypatch)
    bot_id = _make_bot(client)
    client.post("/api/chat", json={"bot_id": bot_id, "message": "cách chơi"}, headers=H)
    assert calls == []
    assert _events(bot_id)[0].escalated is False


def test_disabled_forward_does_not_send(client, monkeypatch):
    _mock_turn(monkeypatch, degraded=True)
    calls = _record_sends(monkeypatch)
    bot_id = _make_bot(client, telegram_forward_enabled=False)
    client.post("/api/chat", json={"bot_id": bot_id, "message": "khó"}, headers=H)
    assert calls == []


def test_missing_token_does_not_send(client, monkeypatch):
    _mock_turn(monkeypatch, degraded=True)
    calls = _record_sends(monkeypatch)
    # enabled + group but no token (never set)
    bot_id = client.post("/api/bots", json={"name": "NoTok"}, headers=H).json()["bot"]["id"]
    client.patch(
        f"/api/bots/{bot_id}",
        json={"telegram_forward_enabled": True, "telegram_group_id": "-1"},
        headers=H,
    )
    client.post("/api/chat", json={"bot_id": bot_id, "message": "khó"}, headers=H)
    assert calls == []


# --- write-only token + fields ------------------------------------------------


def test_token_is_write_only(client):
    bot_id = _make_bot(client, escalation_topics="nạp tiền, lỗi game")
    bot = client.get(f"/api/bots/{bot_id}", headers=H).json()["bot"]
    assert bot["telegram_forward_enabled"] is True
    assert bot["telegram_group_id"] == "-999"
    assert bot["escalation_topics"] == "nạp tiền, lỗi game"
    assert bot["telegram_bot_token_set"] is True
    assert "telegram_bot_token" not in bot


def test_blank_token_keeps_stored(client):
    bot_id = _make_bot(client)
    client.patch(f"/api/bots/{bot_id}", json={"telegram_group_id": "-42", "telegram_bot_token": ""},
                 headers=H)
    from app.db.database import get_session
    from app.db.repository import BotRepository

    with get_session() as s:
        bot = BotRepository(s).get(bot_id)
        assert bot.telegram_group_id == "-42"
        assert bot.telegram_bot_token == "tg-tok"  # unchanged


# --- stats --------------------------------------------------------------------


def test_overview_counts_escalated(client, monkeypatch):
    _mock_turn(monkeypatch, degraded=True)
    _mock_summary(monkeypatch)
    _record_sends(monkeypatch)
    bot_id = _make_bot(client)
    client.post("/api/chat", json={"bot_id": bot_id, "message": "khó 1"}, headers=H)
    client.post("/api/chat", json={"bot_id": bot_id, "message": "khó 2"}, headers=H)

    from app.services import stats_service

    ov = stats_service.overview("owner-1", bot_id, "all")
    assert ov["totals"]["escalated_count"] == 2


# --- test endpoint ------------------------------------------------------------


def test_telegram_test_endpoint_owner_scoped(client, monkeypatch):
    _record_sends(monkeypatch)
    bot_id = _make_bot(client)
    assert client.post(f"/api/bots/{bot_id}/telegram/test", json={},
                       headers={"X-UID": "intruder"}).status_code == 404
    r = client.post(f"/api/bots/{bot_id}/telegram/test", json={}, headers=H)
    assert r.status_code == 200
    assert r.json()["ok"] is True

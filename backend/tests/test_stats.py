"""Usage analytics: event capture + aggregation for the CS dashboard.

Two layers are proven here:
1. Capture — every real chat turn (web + Messenger) writes one ``MessageEvent``;
   the operator self-test (simulate) must NOT pollute the stats.
2. Aggregation — overview KPIs, per-player rollups, and conversation replay,
   all owner-scoped. LLM/Facebook I/O is mocked (no network).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

H = {"X-UID": "owner-1"}


# --- helpers ------------------------------------------------------------------


def _make_bot(client, **fields) -> str:
    bot_id = client.post("/api/bots", json={"name": "FB Bot"}, headers=H).json()["bot"]["id"]
    if fields:
        client.patch(f"/api/bots/{bot_id}", json=fields, headers=H)
    return bot_id


def _mock_turn(monkeypatch, *, degraded: bool = False, reply: str | None = None):
    from app.services.agent_service import TurnResult, agent_service

    async def fake_turn(bot, documents, message, uid, session_id):
        return TurnResult(
            reply=reply or f"echo: {message}",
            category="nạp thẻ",
            delay=0.5,
            degraded=degraded,
        )

    monkeypatch.setattr(agent_service, "run_turn", fake_turn)


def _mute_sends(monkeypatch):
    async def ok(*a, **k):
        return True

    monkeypatch.setattr("app.channels.messenger.send_text", ok)
    monkeypatch.setattr("app.channels.messenger.send_typing", ok)


def _seed_event(bot_id, *, channel="web", sender_id="p1", session_id=None,
                question="q", reply="r", category="khác", latency_ms=400,
                degraded=False, created_at=None):
    """Insert a MessageEvent directly so aggregation can be tested at fixed times."""
    from app.db.database import get_session
    from app.db.models import MessageEvent

    with get_session() as session:
        session.add(MessageEvent(
            bot_id=bot_id,
            channel=channel,
            sender_id=sender_id,
            session_id=session_id or f"{channel}-{sender_id}",
            question=question,
            reply=reply,
            category=category,
            latency_ms=latency_ms,
            degraded=degraded,
            created_at=created_at or datetime.now(UTC),
        ))


def _fetch_events(bot_id):
    """Load events detached so attribute access survives the closed session."""
    from app.db.database import get_session
    from app.db.repository import MessageEventRepository

    with get_session() as session:
        events = MessageEventRepository(session).events_since(bot_id, None)
        session.expunge_all()
    return events


def _count_events(bot_id) -> int:
    from sqlmodel import func, select

    from app.db.database import get_session
    from app.db.models import MessageEvent

    with get_session() as session:
        return session.exec(
            select(func.count()).select_from(MessageEvent).where(MessageEvent.bot_id == bot_id)
        ).one()


# --- capture ------------------------------------------------------------------


def test_web_chat_logs_one_event(client, monkeypatch):
    _mock_turn(monkeypatch)
    bot_id = _make_bot(client)

    r = client.post("/api/chat", json={"bot_id": bot_id, "message": "nạp thẻ sao"}, headers=H)
    assert r.status_code == 200

    events = _fetch_events(bot_id)
    assert len(events) == 1
    ev = events[0]
    assert ev.channel == "web"
    assert ev.sender_id == "owner-1"
    assert ev.question == "nạp thẻ sao"
    assert ev.reply == "echo: nạp thẻ sao"
    assert ev.category == "nạp thẻ"
    assert ev.latency_ms >= 0
    assert ev.degraded is False


def test_messenger_logs_but_simulate_does_not(client, monkeypatch):
    _mock_turn(monkeypatch)
    _mute_sends(monkeypatch)
    bot_id = _make_bot(
        client,
        messenger_enabled=True,
        messenger_page_id="PAGE1",
        messenger_page_token="ptok",
        messenger_app_secret="s3cret",
    )

    # Operator self-test: must not count toward stats.
    client.post(f"/api/bots/{bot_id}/messenger/simulate", json={"message": "thử"}, headers=H)
    assert _count_events(bot_id) == 0

    # A real inbound message: counts, channel=messenger.
    body = {
        "object": "page",
        "entry": [{"id": "PAGE1", "messaging": [
            {"sender": {"id": "PSID9"}, "message": {"text": "xin chào"}}
        ]}],
    }
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(b"s3cret", raw, hashlib.sha256).hexdigest()
    client.post("/api/webhooks/messenger", content=raw,
                headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig})

    events = _fetch_events(bot_id)
    assert len(events) == 1
    assert events[0].channel == "messenger"
    # The player's stable identity is the per-channel uid used for the memory thread.
    assert events[0].sender_id == "fb-PSID9"


def test_degraded_turn_is_flagged(client, monkeypatch):
    _mock_turn(monkeypatch, degraded=True)
    bot_id = _make_bot(client)
    client.post("/api/chat", json={"bot_id": bot_id, "message": "câu khó"}, headers=H)

    events = _fetch_events(bot_id)
    assert events[0].degraded is True


# --- aggregation: overview ----------------------------------------------------


def test_overview_aggregates_kpis(client):
    bot_id = _make_bot(client)
    now = datetime.now(UTC)
    # two players, one returning across days; one degraded; two channels.
    _seed_event(bot_id, sender_id="p1", channel="web", category="nạp thẻ",
                latency_ms=200, created_at=now - timedelta(days=2))
    _seed_event(bot_id, sender_id="p1", channel="web", category="nạp thẻ",
                latency_ms=600, created_at=now - timedelta(hours=1))
    _seed_event(bot_id, sender_id="p2", channel="messenger", category="lỗi game",
                latency_ms=400, degraded=True, question="bug gì đó",
                created_at=now - timedelta(hours=2))

    from app.services import stats_service

    ov = stats_service.overview("owner-1", bot_id, "7d")
    t = ov["totals"]
    assert t["players"] == 2
    assert t["messages"] == 3
    assert t["degraded_count"] == 1
    # 1 of 3 degraded → ~67% auto-answered.
    assert 66 <= t["auto_answer_rate"] <= 67
    # channels both represented.
    assert {c["channel"] for c in ov["by_channel"]} == {"web", "messenger"}
    # top category present.
    assert ov["top_categories"][0]["category"] == "nạp thẻ"
    assert ov["top_categories"][0]["count"] == 2
    # the degraded question surfaces in the "bot bí" list.
    assert any(u["question"] == "bug gì đó" for u in ov["unanswered"])
    # daily series spans the seeded days.
    assert sum(d["count"] for d in ov["messages_per_day"]) == 3


def test_overview_respects_range(client):
    bot_id = _make_bot(client)
    now = datetime.now(UTC)
    _seed_event(bot_id, sender_id="old", created_at=now - timedelta(days=40))
    _seed_event(bot_id, sender_id="recent", created_at=now - timedelta(days=1))

    from app.services import stats_service

    assert stats_service.overview("owner-1", bot_id, "7d")["totals"]["messages"] == 1
    assert stats_service.overview("owner-1", bot_id, "all")["totals"]["messages"] == 2


def test_overview_empty_bot_is_zeroed(client):
    bot_id = _make_bot(client)
    from app.services import stats_service

    ov = stats_service.overview("owner-1", bot_id, "all")
    assert ov["totals"]["messages"] == 0
    assert ov["totals"]["players"] == 0
    assert ov["messages_per_day"] == []
    assert ov["unanswered"] == []


# --- aggregation: players + conversation --------------------------------------


def test_players_rollup(client):
    bot_id = _make_bot(client)
    now = datetime.now(UTC)
    _seed_event(bot_id, sender_id="p1", created_at=now - timedelta(hours=3))
    _seed_event(bot_id, sender_id="p1", created_at=now - timedelta(hours=1))
    _seed_event(bot_id, sender_id="p2", created_at=now - timedelta(hours=2))

    from app.services import stats_service

    players = stats_service.players("owner-1", bot_id, "all")
    by_id = {p["sender_id"]: p for p in players}
    assert by_id["p1"]["message_count"] == 2
    assert by_id["p2"]["message_count"] == 1


def test_conversation_is_ordered(client):
    bot_id = _make_bot(client)
    now = datetime.now(UTC)
    _seed_event(bot_id, sender_id="p1", question="đầu", created_at=now - timedelta(minutes=5))
    _seed_event(bot_id, sender_id="p1", question="sau", created_at=now - timedelta(minutes=1))
    _seed_event(bot_id, sender_id="other", question="khác", created_at=now)

    from app.services import stats_service

    convo = stats_service.conversation("owner-1", bot_id, "web", "p1")
    assert [c["question"] for c in convo] == ["đầu", "sau"]


# --- owner scoping ------------------------------------------------------------


def test_stats_endpoints_require_ownership(client):
    bot_id = _make_bot(client)
    intruder = {"X-UID": "intruder"}
    assert client.get(f"/api/bots/{bot_id}/stats/overview", headers=intruder).status_code == 404
    assert client.get(f"/api/bots/{bot_id}/stats/players", headers=intruder).status_code == 404
    assert client.get(
        f"/api/bots/{bot_id}/stats/conversation?channel=web&sender_id=p1", headers=intruder
    ).status_code == 404


def test_overview_endpoint_returns_json(client):
    bot_id = _make_bot(client)
    _seed_event(bot_id, sender_id="p1")
    r = client.get(f"/api/bots/{bot_id}/stats/overview?range=all", headers=H)
    assert r.status_code == 200
    assert r.json()["totals"]["messages"] == 1

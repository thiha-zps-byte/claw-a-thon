"""Usage analytics for the CS dashboard.

Turns the raw ``message_events`` log into operator-facing numbers: every metric here
maps to a CS decision (staffing, knowledge gaps, channel focus) — see the dashboard.

All reads are owner-scoped. Aggregation runs in Python over the event list (the data
is modest for this SQLite phase); a future Postgres move can push these to SQL.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from app.core.errors import not_found
from app.db.database import get_session
from app.db.models import MessageEvent
from app.db.repository import BotRepository, MessageEventRepository

# How far back each range looks. ``all`` → no lower bound.
_RANGE_DAYS = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}
_UNANSWERED_LIMIT = 50
_TOP_CATEGORIES = 8


def _naive_utc(dt: datetime) -> datetime:
    """Drop tz so SQLite-roundtripped (naive) and fresh (aware) times compare safely."""
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def _since(range_: str) -> datetime | None:
    days = _RANGE_DAYS.get(range_)
    if days is None:
        return None  # "all" or anything unknown → no lower bound
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)


def _owned_bot(uid: str, bot_id: str):
    with get_session() as session:
        bot = BotRepository(session).get_for_owner(bot_id, uid)
        if bot is None:
            raise not_found("Không tìm thấy bot này.")


def _events(bot_id: str, since: datetime | None) -> list[MessageEvent]:
    with get_session() as session:
        events = MessageEventRepository(session).events_since(bot_id, None)
        session.expunge_all()
    if since is not None:
        events = [e for e in events if _naive_utc(e.created_at) >= since]
    return events


def _percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    # Nearest-rank.
    k = max(0, min(len(ordered) - 1, round(pct / 100 * len(ordered)) - 1))
    return int(ordered[k])


# --- public API ---------------------------------------------------------------


def overview(uid: str, bot_id: str, range_: str = "7d") -> dict:
    _owned_bot(uid, bot_id)
    since = _since(range_)
    events = _events(bot_id, since)

    messages = len(events)
    players_in_range = {(e.channel, e.sender_id) for e in events}
    degraded = [e for e in events if e.degraded]
    latencies = [e.latency_ms for e in events]

    # New vs returning: a player is "new" if their first-ever turn for this bot falls
    # inside the window (or the window is "all"). Needs all-time first-seen.
    all_events = _events(bot_id, None)
    first_seen: dict[tuple[str, str], datetime] = {}
    for e in all_events:
        key = (e.channel, e.sender_id)
        ts = _naive_utc(e.created_at)
        if key not in first_seen or ts < first_seen[key]:
            first_seen[key] = ts
    new_players = sum(
        1 for key in players_in_range if since is None or first_seen.get(key, datetime.max) >= since
    )

    # Messages per calendar day (ascending).
    per_day: dict[str, int] = defaultdict(int)
    for e in events:
        per_day[_naive_utc(e.created_at).date().isoformat()] += 1

    by_channel = Counter(e.channel for e in events)
    by_category = Counter(e.category for e in events if e.category)

    unanswered = [
        {
            "sender_id": e.sender_id,
            "channel": e.channel,
            "question": e.question,
            "created_at": _naive_utc(e.created_at).isoformat(),
        }
        for e in sorted(degraded, key=lambda e: _naive_utc(e.created_at), reverse=True)
    ][:_UNANSWERED_LIMIT]

    auto_rate = round(100 * (messages - len(degraded)) / messages) if messages else 0

    return {
        "range": range_,
        "totals": {
            "players": len(players_in_range),
            "new_players": new_players,
            "returning_players": len(players_in_range) - new_players,
            "messages": messages,
            "degraded_count": len(degraded),
            "auto_answer_rate": auto_rate,
            "latency_p50_ms": _percentile(latencies, 50),
            "latency_p95_ms": _percentile(latencies, 95),
        },
        "messages_per_day": [{"date": d, "count": per_day[d]} for d in sorted(per_day)],
        "by_channel": [{"channel": c, "count": n} for c, n in by_channel.most_common()],
        "top_categories": [
            {"category": c, "count": n} for c, n in by_category.most_common(_TOP_CATEGORIES)
        ],
        "unanswered": unanswered,
    }


def players(uid: str, bot_id: str, range_: str = "7d") -> list[dict]:
    _owned_bot(uid, bot_id)
    events = _events(bot_id, _since(range_))

    rollup: dict[tuple[str, str], dict] = {}
    for e in events:
        key = (e.channel, e.sender_id)
        ts = _naive_utc(e.created_at)
        row = rollup.get(key)
        if row is None:
            rollup[key] = {
                "channel": e.channel,
                "sender_id": e.sender_id,
                "message_count": 1,
                "first_at": ts,
                "last_at": ts,
            }
        else:
            row["message_count"] += 1
            row["first_at"] = min(row["first_at"], ts)
            row["last_at"] = max(row["last_at"], ts)

    rows = sorted(rollup.values(), key=lambda r: r["last_at"], reverse=True)
    for r in rows:
        r["first_at"] = r["first_at"].isoformat()
        r["last_at"] = r["last_at"].isoformat()
    return rows


def conversation(uid: str, bot_id: str, channel: str, sender_id: str) -> list[dict]:
    _owned_bot(uid, bot_id)
    with get_session() as session:
        events = MessageEventRepository(session).conversation(bot_id, channel, sender_id)
        session.expunge_all()
    return [
        {
            "question": e.question,
            "reply": e.reply,
            "category": e.category,
            "degraded": e.degraded,
            "created_at": _naive_utc(e.created_at).isoformat(),
        }
        for e in events
    ]

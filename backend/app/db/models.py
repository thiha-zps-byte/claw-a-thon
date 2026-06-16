"""Persistence models (SQLModel).

A ``Bot`` is a CS agent definition owned by a UID. ``player_term`` / ``self_term``
hold the per-game form of address — a first-class field, never buried in docs.
``Document`` holds an uploaded knowledge file with its extracted text cached so we
never re-run OCR/vision on every chat turn.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(UTC)


class Bot(SQLModel, table=True):
    __tablename__ = "bots"

    id: str = Field(default_factory=_uuid, primary_key=True)
    owner_uid: str = Field(index=True)
    name: str
    description: str = ""
    persona: str = ""
    # Form of address (xưng hô) — per game.
    player_term: str = "bạn"          # how the bot addresses the player
    self_term: str = "mình"           # how the bot refers to itself
    tone: str = "thân thiện, chuyên nghiệp"
    # JSON-encoded lists of enabled capability ids.
    enabled_skills: str = "[]"
    enabled_mcp: str = "[]"
    model: str = ""                   # empty → use default LLM_MODEL
    # Shared "công khai" bot: visible read-only to every user; only owner_uid=="admin"
    # may edit. Seeded once on startup. Normal bots leave this False.
    is_shared: bool = False
    # Facebook Messenger channel (per-bot). One Page ⇄ one bot; routing is by page id.
    # Tokens/secret are write-only to the client (see bot_service.bot_to_dict).
    messenger_enabled: bool = False
    messenger_page_id: str = ""
    messenger_verify_token: str = ""  # operator-chosen; matched on the GET handshake
    messenger_page_token: str = ""    # secret — Graph API send
    messenger_app_secret: str = ""    # secret — verifies X-Hub-Signature-256
    created_at: datetime = Field(default_factory=_now)

    def skills(self) -> list[str]:
        try:
            return list(json.loads(self.enabled_skills or "[]"))
        except (ValueError, TypeError):
            return []

    def mcp(self) -> list[str]:
        try:
            return list(json.loads(self.enabled_mcp or "[]"))
        except (ValueError, TypeError):
            return []


class MessageEvent(SQLModel, table=True):
    """One chat turn, recorded for the usage dashboard.

    Denormalized on purpose: a "player" and a "conversation" are derived by grouping
    on ``sender_id`` / ``session_id`` rather than kept in separate tables. Written
    once per real turn from ``bot_service.chat`` (web + Messenger); the operator
    self-test (simulate) is excluded so it never pollutes the numbers.
    """

    __tablename__ = "message_events"

    id: str = Field(default_factory=_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=_now, index=True)
    bot_id: str = Field(index=True, foreign_key="bots.id")
    channel: str = "web"              # web | messenger
    sender_id: str = Field(default="", index=True)   # uid (web) / PSID (messenger)
    session_id: str = Field(default="", index=True)
    question: str = ""
    reply: str = ""
    category: str = ""
    latency_ms: int = 0
    degraded: bool = False            # bot fell back / couldn't answer


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: str = Field(default_factory=_uuid, primary_key=True)
    bot_id: str = Field(index=True, foreign_key="bots.id")
    filename: str
    mime: str = ""
    extracted_text: str = ""
    char_count: int = 0
    status: str = "ready"             # ready | failed
    note: str = ""                    # failure reason, if any
    created_at: datetime = Field(default_factory=_now)

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

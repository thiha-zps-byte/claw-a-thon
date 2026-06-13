"""Repository + persistence tests."""

from __future__ import annotations

from app.db.database import get_session, reset_engine
from app.db.models import Bot, Document
from app.db.repository import BotRepository, DocumentRepository


def test_create_and_scope_by_owner():
    with get_session() as s:
        repo = BotRepository(s)
        repo.create(Bot(owner_uid="alice", name="A"))
        repo.create(Bot(owner_uid="bob", name="B"))
    with get_session() as s:
        repo = BotRepository(s)
        assert len(repo.list_for_owner("alice")) == 1
        assert repo.list_for_owner("alice")[0].name == "A"


def test_persistence_across_engine_reset(sample_bot):
    """A bot survives an engine reset (simulated restart)."""
    bot_id = sample_bot["id"]
    reset_engine()
    with get_session() as s:
        bot = BotRepository(s).get(bot_id)
        assert bot is not None
        assert bot.name == "ZingSpeed Mobile"


def test_delete_bot_cascades_documents():
    with get_session() as s:
        repo = BotRepository(s)
        bot = repo.create(Bot(owner_uid="o", name="X"))
        DocumentRepository(s).add(Document(bot_id=bot.id, filename="d.md", extracted_text="hi", char_count=2))
    with get_session() as s:
        repo = BotRepository(s)
        bot = repo.list_for_owner("o")[0]
        repo.delete(bot)
    with get_session() as s:
        assert DocumentRepository(s).list_for_bot(bot.id) == []

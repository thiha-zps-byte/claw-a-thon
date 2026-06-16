"""Repository layer — the only place that talks to the ORM.

Keeping queries here (rather than in services/routes) means a future swap of the
storage engine is contained to this module.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from app.db.models import Bot, Document, MessageEvent


class BotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, bot: Bot) -> Bot:
        self.session.add(bot)
        self.session.flush()
        self.session.refresh(bot)
        return bot

    def get(self, bot_id: str) -> Bot | None:
        return self.session.get(Bot, bot_id)

    def get_for_owner(self, bot_id: str, owner_uid: str) -> Bot | None:
        bot = self.session.get(Bot, bot_id)
        if bot is None or bot.owner_uid != owner_uid:
            return None
        return bot

    def list_for_owner(self, owner_uid: str) -> list[Bot]:
        stmt = select(Bot).where(Bot.owner_uid == owner_uid).order_by(Bot.created_at.desc())
        return list(self.session.exec(stmt).all())

    def list_all(self) -> list[Bot]:
        return list(self.session.exec(select(Bot)).all())

    def update(self, bot: Bot) -> Bot:
        self.session.add(bot)
        self.session.flush()
        self.session.refresh(bot)
        return bot

    def delete(self, bot: Bot) -> None:
        for doc in self.documents_of(bot.id):
            self.session.delete(doc)
        # Flush child deletes before removing the parent so the FK constraint
        # (documents.bot_id -> bots.id) is satisfied within the transaction.
        self.session.flush()
        self.session.delete(bot)

    def documents_of(self, bot_id: str) -> list[Document]:
        stmt = select(Document).where(Document.bot_id == bot_id).order_by(Document.created_at)
        return list(self.session.exec(stmt).all())

    # --- Messenger routing (no owner context: webhook traffic is public) ---------

    def find_by_messenger_page_id(self, page_id: str) -> Bot | None:
        """The enabled bot bound to a Facebook Page id (routes inbound messages)."""
        if not page_id:
            return None
        stmt = select(Bot).where(
            Bot.messenger_enabled == True,  # noqa: E712 — SQL boolean, not Python truthiness
            Bot.messenger_page_id == page_id,
        )
        return self.session.exec(stmt).first()

    def find_enabled_by_verify_token(self, token: str) -> Bot | None:
        """An enabled bot whose verify token matches (for the GET webhook handshake)."""
        if not token:
            return None
        stmt = select(Bot).where(
            Bot.messenger_enabled == True,  # noqa: E712
            Bot.messenger_verify_token == token,
        )
        return self.session.exec(stmt).first()


class MessageEventRepository:
    """Read/write the usage-analytics event log (see ``stats_service``)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, event: MessageEvent) -> MessageEvent:
        self.session.add(event)
        self.session.flush()
        self.session.refresh(event)
        return event

    def events_since(self, bot_id: str, since: datetime | None) -> list[MessageEvent]:
        stmt = select(MessageEvent).where(MessageEvent.bot_id == bot_id)
        if since is not None:
            stmt = stmt.where(MessageEvent.created_at >= since)
        stmt = stmt.order_by(MessageEvent.created_at)
        return list(self.session.exec(stmt).all())

    def conversation(self, bot_id: str, channel: str, sender_id: str) -> list[MessageEvent]:
        stmt = (
            select(MessageEvent)
            .where(
                MessageEvent.bot_id == bot_id,
                MessageEvent.channel == channel,
                MessageEvent.sender_id == sender_id,
            )
            .order_by(MessageEvent.created_at)
        )
        return list(self.session.exec(stmt).all())


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, document: Document) -> Document:
        self.session.add(document)
        self.session.flush()
        self.session.refresh(document)
        return document

    def get(self, document_id: str) -> Document | None:
        return self.session.get(Document, document_id)

    def list_for_bot(self, bot_id: str) -> list[Document]:
        stmt = select(Document).where(Document.bot_id == bot_id).order_by(Document.created_at)
        return list(self.session.exec(stmt).all())

    def delete(self, document: Document) -> None:
        self.session.delete(document)

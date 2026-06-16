"""Bot business logic: CRUD, document ingestion, and chat dispatch.

Routes stay thin; this is where validation, persistence (via repositories), ingest,
and the agent service come together. Returns plain dicts ready for JSON.
"""

from __future__ import annotations

import json
import time

from app.agents.behavior import triage as _triage  # noqa: F401  (ensures import health)
from app.config import get_settings
from app.core.errors import not_found, validation_error
from app.core.logging import get_logger
from app.db.database import get_session
from app.db.models import Bot, Document
from app.ingest import extract, is_supported
from app.services.agent_service import agent_service
from app.skills import DEFAULT_SKILLS, available_skill_ids

MAX_MESSAGE_CHARS = 4000

_log = get_logger("bot_service")


# --- serialization ------------------------------------------------------------


def bot_to_dict(bot: Bot, doc_count: int | None = None) -> dict:
    data = {
        "id": bot.id,
        "owner_uid": bot.owner_uid,
        "name": bot.name,
        "description": bot.description,
        "persona": bot.persona,
        "player_term": bot.player_term,
        "self_term": bot.self_term,
        "tone": bot.tone,
        "enabled_skills": bot.skills(),
        "enabled_mcp": bot.mcp(),
        "model": bot.model,
        # Shared bot flag — the frontend derives can-edit from owner_uid == current uid.
        "is_shared": bot.is_shared,
        # Messenger channel: non-secret fields are returned as-is; tokens/secret are
        # write-only — we expose only a boolean "is it set" so the UI can show "đã lưu"
        # without ever shipping the secret back to the client.
        "messenger_enabled": bot.messenger_enabled,
        "messenger_page_id": bot.messenger_page_id,
        "messenger_verify_token": bot.messenger_verify_token,
        "messenger_page_token_set": bool(bot.messenger_page_token),
        "messenger_app_secret_set": bool(bot.messenger_app_secret),
        # Telegram escalation: token write-only (boolean flag only); rest as-is.
        "telegram_forward_enabled": bot.telegram_forward_enabled,
        "forward_channel": bot.forward_channel,
        "telegram_group_id": bot.telegram_group_id,
        "escalation_topics": bot.escalation_topics,
        "telegram_bot_token_set": bool(bot.telegram_bot_token),
        "created_at": bot.created_at.isoformat() if bot.created_at else None,
    }
    if doc_count is not None:
        data["document_count"] = doc_count
    return data


def doc_to_dict(doc: Document, include_text: bool = False) -> dict:
    data = {
        "id": doc.id,
        "bot_id": doc.bot_id,
        "filename": doc.filename,
        "mime": doc.mime,
        "char_count": doc.char_count,
        "status": doc.status,
        "note": doc.note,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }
    if include_text:
        data["extracted_text"] = doc.extracted_text
    return data


# --- validation ---------------------------------------------------------------


def _clean_skill_list(raw) -> str:
    """Keep only known skill ids; fall back to the fixed default when nothing valid.

    Skills are not user-selectable, so a bot should always end up with DEFAULT_SKILLS
    (e.g. created with none, or carrying ids that were since removed).
    """
    valid = set(available_skill_ids())
    cleaned = [s for s in raw if s in valid] if isinstance(raw, list) else []
    return json.dumps(cleaned or DEFAULT_SKILLS)


def _apply_messenger_fields(bot: Bot, data: dict) -> None:
    """Copy Messenger channel fields from ``data`` onto ``bot``.

    The secrets (``page_token`` / ``app_secret``) are write-only: an empty/absent
    value leaves the stored secret untouched, so the UI can submit the form without
    knowing the current secret. Non-secret fields are set whenever present.
    """
    if "messenger_enabled" in data and data["messenger_enabled"] is not None:
        bot.messenger_enabled = bool(data["messenger_enabled"])
    for field in ("messenger_page_id", "messenger_verify_token"):
        if field in data and data[field] is not None:
            setattr(bot, field, str(data[field]).strip())
    for field in ("messenger_page_token", "messenger_app_secret"):
        value = (data.get(field) or "").strip()
        if value:
            setattr(bot, field, value)


def _apply_telegram_fields(bot: Bot, data: dict) -> None:
    """Copy Telegram escalation fields from ``data`` onto ``bot``.

    ``telegram_bot_token`` is write-only (blank/absent keeps the stored token).
    """
    if "telegram_forward_enabled" in data and data["telegram_forward_enabled"] is not None:
        bot.telegram_forward_enabled = bool(data["telegram_forward_enabled"])
    for field in ("forward_channel", "telegram_group_id", "escalation_topics"):
        if field in data and data[field] is not None:
            setattr(bot, field, str(data[field]).strip())
    token = (data.get("telegram_bot_token") or "").strip()
    if token:
        bot.telegram_bot_token = token


# --- CRUD ---------------------------------------------------------------------


def create_bot(owner_uid: str, data: dict) -> dict:
    from app.db.repository import BotRepository

    name = (data.get("name") or "").strip()
    if not name:
        raise validation_error("Tên bot không được để trống.")
    bot = Bot(
        owner_uid=owner_uid,
        name=name,
        description=(data.get("description") or "").strip(),
        persona=(data.get("persona") or "").strip(),
        player_term=(data.get("player_term") or "bạn").strip() or "bạn",
        self_term=(data.get("self_term") or "mình").strip() or "mình",
        tone=(data.get("tone") or "thân thiện, chuyên nghiệp").strip(),
        enabled_skills=_clean_skill_list(data.get("enabled_skills")),
        enabled_mcp=json.dumps(data.get("enabled_mcp") or []),
        model=(data.get("model") or "").strip(),
    )
    # Usually configured later (wizard step 3 / Kết nối tab via PATCH), but accept it
    # here too so a single create call can fully provision a bot.
    _apply_messenger_fields(bot, data)
    _apply_telegram_fields(bot, data)
    with get_session() as session:
        repo = BotRepository(session)
        repo.create(bot)
        return bot_to_dict(bot, doc_count=0)


SHARED_BOT_NAME = "Trợ lý CSKH Claw A Thon Game"
SHARED_BOT_OWNER = "admin"


def seed_shared_bot() -> None:
    """Create the shared (công khai) demo bot once — idempotent, runs on startup.

    Owned by ``admin`` and flagged ``is_shared`` so every user can preview it read-only
    while only ``admin`` may edit. Loads the bundled sample docs so it works out of the
    box; ``admin`` configures it further later. Never raises — a seeding failure must
    not block boot.
    """
    from app import sample_docs
    from app.db.repository import BotRepository

    try:
        with get_session() as session:
            repo = BotRepository(session)
            if repo.list_shared():  # already seeded → leave it (admin's edits stay)
                return
            bot = Bot(
                owner_uid=SHARED_BOT_OWNER,
                is_shared=True,
                name=SHARED_BOT_NAME,
                description=(
                    "Bot mẫu dùng chung để mọi người xem thử trợ lý chăm sóc khách hàng "
                    "cho game Claw A Thon."
                ),
                player_term="bạn",
                self_term="mình",
                tone="thân thiện, chuyên nghiệp",
            )
            # Pre-wire the demo Telegram escalation if creds are configured (.env).
            settings = get_settings(require_secrets=False)
            if settings.demo_telegram_token:
                bot.telegram_forward_enabled = True
                bot.forward_channel = "telegram"
                bot.telegram_bot_token = settings.demo_telegram_token
                bot.telegram_group_id = settings.demo_telegram_group_id
            repo.create(bot)
            bot_id = bot.id
        sample_ids = [s["id"] for s in sample_docs.list_samples()]
        if sample_ids:
            add_sample_documents(SHARED_BOT_OWNER, bot_id, sample_ids)
        _log.info("seeded shared bot %s with %d sample docs", bot_id, len(sample_ids))
    except Exception:  # noqa: BLE001
        _log.warning("failed to seed shared bot", exc_info=True)


def list_bots(owner_uid: str) -> list[dict]:
    from app.db.repository import BotRepository

    with get_session() as session:
        repo = BotRepository(session)
        # Own bots + every shared (công khai) bot, deduped (admin owns the shared one).
        bots = repo.list_for_owner(owner_uid)
        own_ids = {b.id for b in bots}
        bots += [b for b in repo.list_shared() if b.id not in own_ids]
        return [bot_to_dict(b, doc_count=len(repo.documents_of(b.id))) for b in bots]


def get_bot_detail(owner_uid: str, bot_id: str) -> dict:
    from app.db.repository import BotRepository

    with get_session() as session:
        repo = BotRepository(session)
        bot = repo.get_viewable(bot_id, owner_uid)
        if bot is None:
            raise not_found("Không tìm thấy bot này.")
        docs = repo.documents_of(bot_id)
        data = bot_to_dict(bot, doc_count=len(docs))
        data["documents"] = [doc_to_dict(d) for d in docs]
        return data


def update_bot(owner_uid: str, bot_id: str, data: dict) -> dict:
    from app.db.repository import BotRepository

    with get_session() as session:
        repo = BotRepository(session)
        bot = repo.get_for_owner(bot_id, owner_uid)
        if bot is None:
            raise not_found("Không tìm thấy bot này.")
        for field in ("name", "description", "persona", "tone", "model"):
            if field in data and data[field] is not None:
                setattr(bot, field, str(data[field]).strip())
        if data.get("player_term"):
            bot.player_term = str(data["player_term"]).strip()
        if data.get("self_term"):
            bot.self_term = str(data["self_term"]).strip()
        if "enabled_skills" in data:
            bot.enabled_skills = _clean_skill_list(data["enabled_skills"])
        if "enabled_mcp" in data:
            bot.enabled_mcp = json.dumps(data["enabled_mcp"] or [])
        _apply_messenger_fields(bot, data)
        _apply_telegram_fields(bot, data)
        repo.update(bot)
        agent_service.invalidate(bot_id)
        return bot_to_dict(bot, doc_count=len(repo.documents_of(bot_id)))


def delete_bot(owner_uid: str, bot_id: str) -> dict:
    from app.db.repository import BotRepository

    with get_session() as session:
        repo = BotRepository(session)
        bot = repo.get_for_owner(bot_id, owner_uid)
        if bot is None:
            raise not_found("Không tìm thấy bot này.")
        if bot.is_shared:
            # Managed fixture: it would respawn on the next startup seed anyway.
            raise validation_error("Không thể xóa bot dùng chung.")
        repo.delete(bot)
    agent_service.invalidate(bot_id)
    return {"deleted": True, "id": bot_id}


# --- documents ----------------------------------------------------------------


def add_documents(owner_uid: str, bot_id: str, files: list[tuple[str, bytes, str]]) -> list[dict]:
    from app.db.repository import BotRepository, DocumentRepository

    settings = get_settings(require_secrets=False)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    results: list[dict] = []
    with get_session() as session:
        bot_repo = BotRepository(session)
        bot = bot_repo.get_for_owner(bot_id, owner_uid)
        if bot is None:
            raise not_found("Không tìm thấy bot này.")
        doc_repo = DocumentRepository(session)
        for filename, content, mime in files:
            if len(content) > max_bytes:
                from app.core.errors import upload_too_large

                raise upload_too_large(settings.max_upload_mb)
            if not is_supported(filename):
                from app.core.errors import unsupported_format

                raise unsupported_format(detail=filename)
            result = extract(filename, content, mime)
            doc = Document(
                bot_id=bot_id,
                filename=filename,
                mime=result.mime or mime,
                extracted_text=result.text,
                char_count=result.char_count,
                status=result.status,
                note=result.note,
            )
            doc_repo.add(doc)
            # Keep the original bytes so the UI can preview the real file (image/PDF…),
            # even when text extraction failed (e.g. a scanned PDF still renders).
            from app import storage

            storage.save_raw(doc.id, filename, content)
            results.append(doc_to_dict(doc))
    agent_service.invalidate(bot_id)
    return results


def add_sample_documents(owner_uid: str, bot_id: str, sample_ids: list[str]) -> list[dict]:
    """Ingest one or more bundled sample docs into a bot (same path as upload)."""
    from app import sample_docs

    files: list[tuple[str, bytes, str]] = []
    for sid in sample_ids:
        item = sample_docs.read_sample_bytes(str(sid))
        if item is None:
            raise not_found(f"Không tìm thấy tài liệu mẫu: {sid}")
        filename, content = item
        files.append((filename, content, ""))
    if not files:
        raise validation_error("Chưa chọn tài liệu mẫu nào.")
    return add_documents(owner_uid, bot_id, files)


def get_document(owner_uid: str, bot_id: str, doc_id: str) -> dict:
    """Return one document including its extracted text (for preview)."""
    from app.db.repository import BotRepository, DocumentRepository

    with get_session() as session:
        bot = BotRepository(session).get_viewable(bot_id, owner_uid)
        if bot is None:
            raise not_found("Không tìm thấy bot này.")
        doc = DocumentRepository(session).get(doc_id)
        if doc is None or doc.bot_id != bot_id:
            raise not_found("Không tìm thấy tài liệu này.")
        return doc_to_dict(doc, include_text=True)


def get_document_raw(owner_uid: str, bot_id: str, doc_id: str) -> tuple[bytes, str, str]:
    """Return (raw bytes, mime, filename) of an uploaded document (viewable bots)."""
    from app import storage
    from app.db.repository import BotRepository, DocumentRepository

    with get_session() as session:
        bot = BotRepository(session).get_viewable(bot_id, owner_uid)
        if bot is None:
            raise not_found("Không tìm thấy bot này.")
        doc = DocumentRepository(session).get(doc_id)
        if doc is None or doc.bot_id != bot_id:
            raise not_found("Không tìm thấy tài liệu này.")
        raw = storage.read_raw(doc.id, doc.filename)
        if raw is None:
            raise not_found("Không tìm thấy file gốc của tài liệu này.")
        mime = doc.mime or storage.mime_for(doc.filename)
        return raw, mime, doc.filename


def list_documents(owner_uid: str, bot_id: str) -> list[dict]:
    from app.db.repository import BotRepository, DocumentRepository

    with get_session() as session:
        bot = BotRepository(session).get_viewable(bot_id, owner_uid)
        if bot is None:
            raise not_found("Không tìm thấy bot này.")
        docs = DocumentRepository(session).list_for_bot(bot_id)
        return [doc_to_dict(d) for d in docs]


def delete_document(owner_uid: str, bot_id: str, doc_id: str) -> dict:
    from app.db.repository import BotRepository, DocumentRepository

    with get_session() as session:
        bot = BotRepository(session).get_for_owner(bot_id, owner_uid)
        if bot is None:
            raise not_found("Không tìm thấy bot này.")
        doc_repo = DocumentRepository(session)
        doc = doc_repo.get(doc_id)
        if doc is None or doc.bot_id != bot_id:
            raise not_found("Không tìm thấy tài liệu này.")
        doc_repo.delete(doc)
    from app import storage

    storage.delete_raw(doc_id, doc.filename)
    agent_service.invalidate(bot_id)
    return {"deleted": True, "id": doc_id}


# --- chat ---------------------------------------------------------------------


async def chat(
    uid: str,
    bot_id: str,
    message: str,
    session_id: str,
    *,
    require_owner: bool = False,
    channel: str = "web",
    log_event: bool = True,
) -> dict:
    """Run one chat turn.

    ``require_owner`` scopes the bot to ``uid`` (used by the web studio's
    ``/api/chat`` so one user can't drive another user's bot). The public runtime
    entrypoint (``/invocations``) leaves it off — there the player is not the owner.

    Every real turn is recorded as a ``MessageEvent`` for the usage dashboard.
    ``log_event=False`` skips that (used by the Messenger operator self-test so a
    dry-run never pollutes the stats). ``channel`` tags where the turn came from.
    """
    from app.db.repository import BotRepository

    message = (message or "").strip()
    if not message:
        raise validation_error("Tin nhắn trống.")
    if len(message) > MAX_MESSAGE_CHARS:
        message = message[:MAX_MESSAGE_CHARS]

    # Load bot + documents, detach so the LLM call doesn't hold a DB connection.
    # ``require_owner`` (web studio) still lets anyone chat a shared (công khai) bot —
    # preview is open; only writes stay owner-scoped.
    with get_session() as session:
        repo = BotRepository(session)
        bot = repo.get_viewable(bot_id, uid) if require_owner else repo.get(bot_id)
        if bot is None:
            raise not_found("Bot không tồn tại hoặc đã bị xóa. Vui lòng chọn bot khác.")
        documents = repo.documents_of(bot_id)
        session.expunge_all()

    started = time.perf_counter()
    result = await agent_service.run_turn(bot, documents, message, uid, session_id)
    latency_ms = int((time.perf_counter() - started) * 1000)

    # Hard case → forward a one-way summary to the human support group (best-effort).
    escalated = await _maybe_forward(bot, channel, uid, message, result)

    if log_event:
        _record_event(bot_id, channel, uid, session_id, message, result, latency_ms, escalated)

    return {
        "reply": result.reply,
        "category": result.category,
        "delay": result.delay,
        "bot_id": bot_id,
    }


_CHANNEL_LABELS = {"web": "Web", "messenger": "Messenger"}


def _ticket_text(bot: Bot, channel: str, sender_id: str, summary: str) -> str:
    """Build the support ticket as a Telegram code block (<pre> → monospace box).

    Dynamic parts are HTML-escaped (still required inside <pre>).
    """
    import html
    from datetime import UTC, datetime

    now = datetime.now(UTC).strftime("%H:%M - %d/%m/%Y")
    src = _CHANNEL_LABELS.get(channel, channel)
    e = html.escape
    body = (
        f"📌 [TICKET] — {e(bot.name)}\n"
        f"• Nguồn: {e(src)}\n"
        f"• Người chơi: {e(sender_id)}\n"
        f"• Thời gian: {now}\n"
        f"• Nội dung: {e(summary)}"
    )
    return f"<pre>{body}</pre>"


async def _maybe_forward(bot: Bot, channel: str, sender_id: str, question: str, result) -> bool:
    """Forward a support ticket to the Telegram group on a hard case. Never raises."""
    should = result.degraded or result.needs_human
    if not (
        should
        and bot.telegram_forward_enabled
        and bot.telegram_bot_token
        and bot.telegram_group_id
    ):
        return False
    import asyncio

    from app.agents.behavior import escalation
    from app.channels import telegram

    try:
        summary = await asyncio.to_thread(escalation.summarize, question)
        text = _ticket_text(bot, channel, sender_id, summary or question)
        return await telegram.send_message(
            bot.telegram_bot_token, bot.telegram_group_id, text, parse_mode="HTML"
        )
    except Exception:  # noqa: BLE001 — forwarding must never break a reply
        _log.warning("telegram forward failed for bot %s", bot.id, exc_info=True)
        return False


def _record_event(
    bot_id, channel, sender_id, session_id, question, result, latency_ms, escalated=False
) -> None:
    """Persist one usage event. Never let analytics break a chat reply."""
    from app.db.models import MessageEvent
    from app.db.repository import MessageEventRepository

    try:
        with get_session() as session:
            MessageEventRepository(session).add(
                MessageEvent(
                    bot_id=bot_id,
                    channel=channel,
                    sender_id=sender_id,
                    session_id=session_id,
                    question=question,
                    reply=result.reply,
                    category=result.category,
                    latency_ms=latency_ms,
                    degraded=result.degraded,
                    escalated=escalated,
                )
            )
    except Exception:  # noqa: BLE001
        _log.warning("failed to record message event for bot %s", bot_id, exc_info=True)

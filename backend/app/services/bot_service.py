"""Bot business logic: CRUD, document ingestion, and chat dispatch.

Routes stay thin; this is where validation, persistence (via repositories), ingest,
and the agent service come together. Returns plain dicts ready for JSON.
"""

from __future__ import annotations

import json

from app.agents.behavior import triage as _triage  # noqa: F401  (ensures import health)
from app.config import get_settings
from app.core.errors import not_found, validation_error
from app.db.database import get_session
from app.db.models import Bot, Document
from app.ingest import extract, is_supported
from app.services.agent_service import agent_service
from app.skills import DEFAULT_SKILLS, available_skill_ids

MAX_MESSAGE_CHARS = 4000


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
        # Messenger channel: non-secret fields are returned as-is; tokens/secret are
        # write-only — we expose only a boolean "is it set" so the UI can show "đã lưu"
        # without ever shipping the secret back to the client.
        "messenger_enabled": bot.messenger_enabled,
        "messenger_page_id": bot.messenger_page_id,
        "messenger_verify_token": bot.messenger_verify_token,
        "messenger_page_token_set": bool(bot.messenger_page_token),
        "messenger_app_secret_set": bool(bot.messenger_app_secret),
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
    with get_session() as session:
        repo = BotRepository(session)
        repo.create(bot)
        return bot_to_dict(bot, doc_count=0)


def list_bots(owner_uid: str) -> list[dict]:
    from app.db.repository import BotRepository

    with get_session() as session:
        repo = BotRepository(session)
        bots = repo.list_for_owner(owner_uid)
        return [bot_to_dict(b, doc_count=len(repo.documents_of(b.id))) for b in bots]


def get_bot_detail(owner_uid: str, bot_id: str) -> dict:
    from app.db.repository import BotRepository

    with get_session() as session:
        repo = BotRepository(session)
        bot = repo.get_for_owner(bot_id, owner_uid)
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
        bot = BotRepository(session).get_for_owner(bot_id, owner_uid)
        if bot is None:
            raise not_found("Không tìm thấy bot này.")
        doc = DocumentRepository(session).get(doc_id)
        if doc is None or doc.bot_id != bot_id:
            raise not_found("Không tìm thấy tài liệu này.")
        return doc_to_dict(doc, include_text=True)


def get_document_raw(owner_uid: str, bot_id: str, doc_id: str) -> tuple[bytes, str, str]:
    """Return (raw bytes, mime, filename) of an uploaded document, owner-scoped."""
    from app import storage
    from app.db.repository import BotRepository, DocumentRepository

    with get_session() as session:
        bot = BotRepository(session).get_for_owner(bot_id, owner_uid)
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
        bot = BotRepository(session).get_for_owner(bot_id, owner_uid)
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
    uid: str, bot_id: str, message: str, session_id: str, *, require_owner: bool = False
) -> dict:
    """Run one chat turn.

    ``require_owner`` scopes the bot to ``uid`` (used by the web studio's
    ``/api/chat`` so one user can't drive another user's bot). The public runtime
    entrypoint (``/invocations``) leaves it off — there the player is not the owner.
    """
    from app.db.repository import BotRepository

    message = (message or "").strip()
    if not message:
        raise validation_error("Tin nhắn trống.")
    if len(message) > MAX_MESSAGE_CHARS:
        message = message[:MAX_MESSAGE_CHARS]

    # Load bot + documents, detach so the LLM call doesn't hold a DB connection.
    with get_session() as session:
        repo = BotRepository(session)
        bot = repo.get_for_owner(bot_id, uid) if require_owner else repo.get(bot_id)
        if bot is None:
            raise not_found("Bot không tồn tại hoặc đã bị xóa. Vui lòng chọn bot khác.")
        documents = repo.documents_of(bot_id)
        session.expunge_all()

    result = await agent_service.run_turn(bot, documents, message, uid, session_id)
    return {
        "reply": result.reply,
        "category": result.category,
        "delay": result.delay,
        "bot_id": bot_id,
    }

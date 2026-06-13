"""Bot / document / chat HTTP routes (Starlette handlers).

Registered on the GreenNodeAgentBaseApp in ``main.py``. Each handler is wrapped with
``handle_errors`` so failures become the unified error envelope.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app import sample_docs, storage
from app.api.http import get_uid, handle_errors, json_response, read_json
from app.config import get_settings
from app.core.errors import not_found, upload_too_large, validation_error
from app.services import bot_service
from app.skills import available_skills


@handle_errors
async def bots_collection(request: Request) -> JSONResponse:
    """GET /api/bots → list (owner-scoped); POST /api/bots → create."""
    uid = get_uid(request)
    if request.method == "POST":
        body = await read_json(request)
        return json_response({"bot": bot_service.create_bot(uid, body)}, status=201)
    return json_response({"bots": bot_service.list_bots(uid)})


@handle_errors
async def bot_item(request: Request) -> JSONResponse:
    """GET / PATCH / DELETE /api/bots/{bot_id}."""
    uid = get_uid(request)
    bot_id = request.path_params["bot_id"]
    if request.method == "DELETE":
        return json_response(bot_service.delete_bot(uid, bot_id))
    if request.method in ("PATCH", "PUT"):
        body = await read_json(request)
        return json_response({"bot": bot_service.update_bot(uid, bot_id, body)})
    return json_response({"bot": bot_service.get_bot_detail(uid, bot_id)})


@handle_errors
async def bot_documents(request: Request) -> JSONResponse:
    """GET → list documents; POST → upload (multipart) documents for a bot."""
    uid = get_uid(request)
    bot_id = request.path_params["bot_id"]
    if request.method == "POST":
        # Reject an oversized body up front (before buffering the multipart payload)
        # as a coarse anti-DoS cap; the precise per-file limit is enforced below.
        settings = get_settings(require_secrets=False)
        body_ceiling = settings.max_upload_mb * 1024 * 1024 * 4
        clen = request.headers.get("content-length")
        if clen and clen.isdigit() and int(clen) > body_ceiling:
            raise upload_too_large(settings.max_upload_mb)
        form = await request.form()
        uploads = form.getlist("files") or form.getlist("file")
        if not uploads:
            raise validation_error("Chưa chọn file nào để tải lên.")
        files: list[tuple[str, bytes, str]] = []
        for up in uploads:
            if not hasattr(up, "read"):
                continue
            content = await up.read()
            files.append((up.filename or "untitled", content, up.content_type or ""))
        if not files:
            raise validation_error("Không đọc được file tải lên.")
        docs = bot_service.add_documents(uid, bot_id, files)
        return json_response({"documents": docs}, status=201)
    return json_response({"documents": bot_service.list_documents(uid, bot_id)})


@handle_errors
async def document_item(request: Request) -> JSONResponse:
    """GET → document incl. extracted text (preview); DELETE → remove it."""
    uid = get_uid(request)
    bot_id = request.path_params["bot_id"]
    doc_id = request.path_params["doc_id"]
    if request.method == "GET":
        return json_response({"document": bot_service.get_document(uid, bot_id, doc_id)})
    return json_response(bot_service.delete_document(uid, bot_id, doc_id))


@handle_errors
async def document_raw(request: Request) -> Response:
    """GET /api/bots/{bot_id}/documents/{doc_id}/raw → original file bytes (preview)."""
    uid = get_uid(request)
    bot_id = request.path_params["bot_id"]
    doc_id = request.path_params["doc_id"]
    content, mime, filename = bot_service.get_document_raw(uid, bot_id, doc_id)
    return Response(
        content,
        media_type=mime or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@handle_errors
async def sample_raw(request: Request) -> Response:
    """GET /api/samples/{sample_id}/raw → original sample file bytes (preview)."""
    item = sample_docs.read_sample_bytes(request.path_params["sample_id"])
    if item is None:
        raise not_found("Không tìm thấy tài liệu mẫu này.")
    filename, content = item
    return Response(
        content,
        media_type=storage.mime_for(filename, "text/plain"),
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@handle_errors
async def bot_documents_samples(request: Request) -> JSONResponse:
    """POST /api/bots/{bot_id}/documents/samples → add bundled sample docs to a bot."""
    uid = get_uid(request)
    bot_id = request.path_params["bot_id"]
    body = await read_json(request)
    sample_ids = body.get("sample_ids") or body.get("ids") or []
    if not isinstance(sample_ids, list) or not sample_ids:
        raise validation_error("Chưa chọn tài liệu mẫu nào.")
    docs = bot_service.add_sample_documents(uid, bot_id, sample_ids)
    return json_response({"documents": docs}, status=201)


@handle_errors
async def samples_collection(request: Request) -> JSONResponse:
    """GET /api/samples → catalogue of bundled sample docs."""
    return json_response({"samples": sample_docs.list_samples()})


@handle_errors
async def sample_item(request: Request) -> JSONResponse:
    """GET /api/samples/{sample_id} → full content of a sample (for preview)."""
    sample = sample_docs.get_sample(request.path_params["sample_id"])
    if sample is None:
        raise not_found("Không tìm thấy tài liệu mẫu này.")
    return json_response({"sample": sample})


@handle_errors
async def skills_collection(request: Request) -> JSONResponse:
    """GET /api/skills → available skills (id + Vietnamese label/description)."""
    return json_response({"skills": available_skills()})


@handle_errors
async def chat_endpoint(request: Request) -> JSONResponse:
    """POST /api/chat → chat with a bot (mirror of the /invocations entrypoint).

    Provided so the web frontend has a plain REST endpoint; the GreenNode runtime
    entrypoint (/invocations) shares the same logic.
    """
    uid = get_uid(request)
    body = await read_json(request)
    bot_id = (body.get("bot_id") or body.get("agent_id") or "").strip()
    if not bot_id:
        raise validation_error("Thiếu bot_id.")
    message = body.get("message") or ""
    session_id = (body.get("session_id") or f"web-{uid}").strip()
    # Web studio: a user may only chat with their own bot.
    result = await bot_service.chat(uid, bot_id, message, session_id, require_owner=True)
    return json_response(result)


def register(app) -> None:
    """Attach all routes to the Starlette app."""
    app.add_route("/api/bots", bots_collection, methods=["GET", "POST"])
    app.add_route("/api/bots/{bot_id}", bot_item, methods=["GET", "PATCH", "PUT", "DELETE"])
    app.add_route("/api/bots/{bot_id}/documents", bot_documents, methods=["GET", "POST"])
    # Register the static "samples" sub-path BEFORE the {doc_id} catch so it isn't
    # swallowed as a document id.
    app.add_route(
        "/api/bots/{bot_id}/documents/samples", bot_documents_samples, methods=["POST"]
    )
    app.add_route(
        "/api/bots/{bot_id}/documents/{doc_id}/raw", document_raw, methods=["GET"]
    )
    app.add_route(
        "/api/bots/{bot_id}/documents/{doc_id}", document_item, methods=["GET", "DELETE"]
    )
    app.add_route("/api/samples", samples_collection, methods=["GET"])
    app.add_route("/api/samples/{sample_id}/raw", sample_raw, methods=["GET"])
    app.add_route("/api/samples/{sample_id}", sample_item, methods=["GET"])
    app.add_route("/api/skills", skills_collection, methods=["GET"])
    app.add_route("/api/chat", chat_endpoint, methods=["POST"])

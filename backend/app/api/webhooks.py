"""Facebook Messenger webhook + operator self-test routes.

Public webhook (no UID):
- ``GET  /api/webhooks/messenger``  → verify-token handshake (echo hub.challenge).
- ``POST /api/webhooks/messenger``  → inbound messages; verify HMAC, route by Page id,
  reply via Graph API. Responds 200 immediately and delivers in a background task so
  Facebook never retries (which would double-send).

Owner-scoped helpers (X-UID), so a bot can be proven working before a real Page exists:
- ``POST /api/bots/{bot_id}/messenger/simulate`` → run the exact inbound pipeline with
  delivery skipped; returns what the bot would reply.
- ``POST /api/bots/{bot_id}/messenger/validate`` → check Page id + token against Graph API.

The single ``handle_incoming`` function is shared by the webhook and the simulator, so
a passing simulation reflects real runtime behaviour.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json

import httpx
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response

from app.api.http import get_uid, handle_errors, json_response, read_json
from app.channels import messenger
from app.core.errors import not_found
from app.core.logging import get_logger
from app.db.database import get_session
from app.db.repository import BotRepository
from app.ingest import image_vision
from app.services import bot_service

log = get_logger("webhooks")

# Cap images processed per turn (each costs a vision call).
_MAX_IMAGES = 3


async def _download(url: str) -> tuple[bytes, str]:
    """Fetch an attachment's bytes + mime. Raises on failure (caller handles)."""
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        mime = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        return resp.content, mime or "image/jpeg"


async def _describe_images(image_urls) -> list[str]:
    """Turn each image URL into a text description via the vision model (best-effort)."""
    out: list[str] = []
    for url in list(image_urls)[:_MAX_IMAGES]:
        try:
            raw, mime = await _download(url)
            desc = await asyncio.to_thread(image_vision.extract_image, raw, mime)
            out.append(desc.strip() or "(ảnh không có nội dung đọc được)")
        except Exception as exc:  # noqa: BLE001 — a bad image must not drop the turn
            log.warning("image describe failed: %s", type(exc).__name__)
            out.append("(không đọc được ảnh)")
    return out


def _compose_message(text: str, descriptions: list[str]) -> str:
    """Merge the caption (if any) with image descriptions into one chat message."""
    parts = [p for p in [(text or "").strip()] if p]
    parts += [f"[Ảnh đính kèm] {d}" for d in descriptions]
    return "\n".join(parts) or "[Người dùng gửi một ảnh]"


# --- shared inbound pipeline --------------------------------------------------


async def handle_incoming(
    bot_id: str,
    page_token: str,
    page_id: str,
    psid: str,
    text: str,
    *,
    image_urls=(),
    dry_run: bool = False,
) -> dict:
    """Run one inbound Messenger message through the chat pipeline.

    The player is not the bot's owner, so ``require_owner`` is off. uid/session are
    scoped per (page, sender) so each Messenger user keeps their own memory thread.
    Attached images are read by the vision model and merged into the message.
    When ``dry_run`` is set, the reply is returned but not delivered to Facebook.
    """
    uid = f"fb-{psid}"
    session_id = f"fb-{page_id or 'sim'}-{psid}"
    message = _compose_message(text, await _describe_images(image_urls))
    # A dry-run (operator self-test) must not pollute the usage stats.
    result = await bot_service.chat(
        uid, bot_id, message, session_id, channel="messenger", log_event=not dry_run
    )
    if not dry_run:
        await messenger.send_typing(page_token, psid)
        await messenger.send_text(page_token, psid, result["reply"])
    return result


async def handle_comment(
    bot_id: str,
    page_token: str,
    page_id: str,
    comment_id: str,
    commenter_id: str,
    text: str,
    *,
    image_urls=(),
    dry_run: bool = False,
) -> dict:
    """Answer a Page post comment by sending the commenter a private reply (DM).

    Same chat pipeline as a Messenger DM; routed/scoped per (page, commenter).
    Any photo on the comment is read by the vision model and merged into the message.
    """
    uid = f"fb-{commenter_id}"
    session_id = f"fb-{page_id or 'sim'}-{commenter_id}"
    message = _compose_message(text, await _describe_images(image_urls))
    result = await bot_service.chat(
        uid, bot_id, message, session_id, channel="messenger", log_event=not dry_run
    )
    if not dry_run:
        await messenger.private_reply(page_token, comment_id, result["reply"])
    return result


# --- public webhook -----------------------------------------------------------


def _valid_signature(app_secret: str, raw_body: bytes, header: str) -> bool:
    """Constant-time check of the X-Hub-Signature-256 header against the raw body."""
    if not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


async def _verify_handshake(request: Request) -> Response:
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")
    if mode == "subscribe" and token:
        with get_session() as session:
            bot = BotRepository(session).find_enabled_by_verify_token(token)
        if bot is not None:
            return PlainTextResponse(challenge)
    return PlainTextResponse("Forbidden", status_code=403)


async def _receive_events(request: Request) -> Response:
    raw = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    try:
        data = json.loads(raw or b"{}")
    except (ValueError, TypeError):
        return PlainTextResponse("Bad Request", status_code=400)

    # Always 200 for non-page objects so Facebook stops redelivering.
    if not isinstance(data, dict) or data.get("object") != "page":
        return PlainTextResponse("ok")

    jobs: list[tuple] = []          # (bot_id, page_token, page_id, psid, text, image_urls)
    comment_jobs: list[tuple] = []  # (bot_id, page_token, page_id, comment_id, from_id, text, image_urls)
    with get_session() as session:
        repo = BotRepository(session)
        for entry in data.get("entry", []):
            page_id = str(entry.get("id") or "")
            bot = repo.find_by_messenger_page_id(page_id)
            if bot is None:
                log.warning("messenger event for unknown/disabled page %s", page_id)
                continue
            if bot.messenger_app_secret and not _valid_signature(
                bot.messenger_app_secret, raw, signature
            ):
                log.warning("messenger signature mismatch for page %s", page_id)
                continue
            # Messenger DMs.
            for event in entry.get("messaging", []):
                message = event.get("message") or {}
                if message.get("is_echo"):  # skip our own outbound
                    continue
                text = message.get("text") or ""
                images = [
                    (a.get("payload") or {}).get("url")
                    for a in (message.get("attachments") or [])
                    if a.get("type") == "image" and (a.get("payload") or {}).get("url")
                ]
                psid = (event.get("sender") or {}).get("id")
                # Need a sender and at least text or an image.
                if not psid or not (text or images):
                    continue
                jobs.append(
                    (bot.id, bot.messenger_page_token, page_id, str(psid), text, images)
                )
            # Post comments (feed) → private-reply the commenter.
            for change in entry.get("changes", []):
                if change.get("field") != "feed":
                    continue
                v = change.get("value") or {}
                if v.get("item") != "comment" or v.get("verb") != "add":
                    continue
                from_id = str((v.get("from") or {}).get("id") or "")
                text = v.get("message") or ""
                comment_id = v.get("comment_id")
                photo = v.get("photo")
                images = [photo] if photo else []
                # Skip the Page's own comments (its replies) to avoid an echo loop,
                # and comments with neither text nor a photo.
                if not comment_id or not from_id or from_id == page_id or not (text or images):
                    continue
                comment_jobs.append(
                    (bot.id, bot.messenger_page_token, page_id, str(comment_id), from_id, text, images)
                )

    # Deliver after the response is sent → Facebook gets a prompt 200, no retries.
    return JSONResponse(
        {"status": "ok"},
        background=BackgroundTask(_run_all_jobs, jobs, comment_jobs),
    )


async def _run_all_jobs(jobs, comment_jobs) -> None:
    for bot_id, page_token, page_id, psid, text, images in jobs:
        try:
            await handle_incoming(bot_id, page_token, page_id, psid, text, image_urls=images)
        except Exception as exc:  # noqa: BLE001 — one bad message must not drop the rest
            log.warning("messenger handle failed (bot=%s): %s", bot_id, type(exc).__name__)
    for bot_id, page_token, page_id, comment_id, from_id, text, images in comment_jobs:
        try:
            await handle_comment(
                bot_id, page_token, page_id, comment_id, from_id, text, image_urls=images
            )
        except Exception as exc:  # noqa: BLE001 — one bad comment must not drop the rest
            log.warning("comment handle failed (bot=%s): %s", bot_id, type(exc).__name__)


@handle_errors
async def messenger_webhook(request: Request) -> Response:
    """GET → verify handshake; POST → inbound events."""
    if request.method == "GET":
        return await _verify_handshake(request)
    return await _receive_events(request)


# --- owner-scoped self-test ---------------------------------------------------


@handle_errors
async def messenger_simulate(request: Request) -> JSONResponse:
    """POST /api/bots/{bot_id}/messenger/simulate → dry-run the inbound pipeline."""
    uid = get_uid(request)
    bot_id = request.path_params["bot_id"]
    body = await read_json(request)
    message = (body.get("message") or "").strip()
    psid = (body.get("psid") or f"sim-{uid}").strip()

    # Ownership gate (the chat run itself is public/require_owner=False).
    with get_session() as session:
        bot = BotRepository(session).get_for_owner(bot_id, uid)
        if bot is None:
            raise not_found("Không tìm thấy bot này.")
        page_id = bot.messenger_page_id

    result = await handle_incoming(bot_id, "", page_id, psid, message, dry_run=True)
    return json_response(
        {"reply": result["reply"], "category": result["category"], "delay": result["delay"]}
    )


@handle_errors
async def messenger_validate(request: Request) -> JSONResponse:
    """POST /api/bots/{bot_id}/messenger/validate → check Page id + token via Graph API."""
    uid = get_uid(request)
    bot_id = request.path_params["bot_id"]
    body = await read_json(request)

    with get_session() as session:
        bot = BotRepository(session).get_for_owner(bot_id, uid)
        if bot is None:
            raise not_found("Không tìm thấy bot này.")
        # Allow overrides so the operator can test the values just typed (token is
        # write-only, so a blank token falls back to the stored one).
        page_id = (body.get("page_id") or bot.messenger_page_id or "").strip()
        page_token = (body.get("page_token") or "").strip() or bot.messenger_page_token

    result = await messenger.validate_credentials(page_token, page_id)
    return json_response(result)


@handle_errors
async def messenger_subscribe(request: Request) -> JSONResponse:
    """POST /api/bots/{bot_id}/messenger/subscribe → subscribe the Page to message events.

    Automates the manual "subscribe page" step using the stored Page Access Token.
    """
    uid = get_uid(request)
    bot_id = request.path_params["bot_id"]
    body = await read_json(request)

    with get_session() as session:
        bot = BotRepository(session).get_for_owner(bot_id, uid)
        if bot is None:
            raise not_found("Không tìm thấy bot này.")
        page_token = (body.get("page_token") or "").strip() or bot.messenger_page_token

    result = await messenger.subscribe_page(page_token)
    return json_response(result)


def register(app) -> None:
    app.add_route("/api/webhooks/messenger", messenger_webhook, methods=["GET", "POST"])
    app.add_route(
        "/api/bots/{bot_id}/messenger/simulate", messenger_simulate, methods=["POST"]
    )
    app.add_route(
        "/api/bots/{bot_id}/messenger/validate", messenger_validate, methods=["POST"]
    )
    app.add_route(
        "/api/bots/{bot_id}/messenger/subscribe", messenger_subscribe, methods=["POST"]
    )

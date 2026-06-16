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

import hashlib
import hmac
import json

from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response

from app.api.http import get_uid, handle_errors, json_response, read_json
from app.channels import messenger
from app.core.errors import not_found
from app.core.logging import get_logger
from app.db.database import get_session
from app.db.repository import BotRepository
from app.services import bot_service

log = get_logger("webhooks")


# --- shared inbound pipeline --------------------------------------------------


async def handle_incoming(
    bot_id: str,
    page_token: str,
    page_id: str,
    psid: str,
    text: str,
    *,
    dry_run: bool = False,
) -> dict:
    """Run one inbound Messenger message through the chat pipeline.

    The player is not the bot's owner, so ``require_owner`` is off. uid/session are
    scoped per (page, sender) so each Messenger user keeps their own memory thread.
    When ``dry_run`` is set, the reply is returned but not delivered to Facebook.
    """
    uid = f"fb-{psid}"
    session_id = f"fb-{page_id or 'sim'}-{psid}"
    # A dry-run (operator self-test) must not pollute the usage stats.
    result = await bot_service.chat(
        uid, bot_id, text, session_id, channel="messenger", log_event=not dry_run
    )
    if not dry_run:
        await messenger.send_typing(page_token, psid)
        await messenger.send_text(page_token, psid, result["reply"])
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

    jobs: list[tuple[str, str, str, str, str]] = []
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
            for event in entry.get("messaging", []):
                message = event.get("message") or {}
                text = message.get("text")
                # Skip echoes (our own outbound) and non-text events.
                if not text or message.get("is_echo"):
                    continue
                psid = (event.get("sender") or {}).get("id")
                if not psid:
                    continue
                jobs.append((bot.id, bot.messenger_page_token, page_id, str(psid), text))

    # Deliver after the response is sent → Facebook gets a prompt 200, no retries.
    return JSONResponse({"status": "ok"}, background=BackgroundTask(_run_jobs, jobs))


async def _run_jobs(jobs: list[tuple[str, str, str, str, str]]) -> None:
    for bot_id, page_token, page_id, psid, text in jobs:
        try:
            await handle_incoming(bot_id, page_token, page_id, psid, text)
        except Exception as exc:  # noqa: BLE001 — one bad message must not drop the rest
            log.warning("messenger handle failed (bot=%s): %s", bot_id, type(exc).__name__)


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

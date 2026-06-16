"""Telegram escalation — operator 'test connection' route (owner-scoped)."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.http import get_uid, handle_errors, json_response, read_json
from app.channels import telegram
from app.core.errors import not_found, validation_error
from app.db.database import get_session
from app.db.repository import BotRepository


@handle_errors
async def telegram_test(request: Request) -> JSONResponse:
    """Send a sample message to the bot's support group to verify token + group id."""
    uid = get_uid(request)
    bot_id = request.path_params["bot_id"]
    body = await read_json(request)
    with get_session() as session:
        bot = BotRepository(session).get_for_owner(bot_id, uid)
        if bot is None:
            raise not_found("Không tìm thấy bot này.")
        # Allow overriding from the form so the operator can test before saving.
        token = (body.get("telegram_bot_token") or "").strip() or bot.telegram_bot_token
        group = (body.get("telegram_group_id") or "").strip() or bot.telegram_group_id

    if not token or not group:
        raise validation_error("Thiếu bot token hoặc group id.")
    ok = await telegram.send_message(
        token, group, "✅ Kết nối thành công — tin thử từ CS Agent Studio."
    )
    return json_response({"ok": ok, "error": None if ok else "Gửi thất bại. Kiểm tra token/group id."})


def register(app) -> None:
    app.add_route("/api/bots/{bot_id}/telegram/test", telegram_test, methods=["POST"])

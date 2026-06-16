"""Usage-dashboard routes (owner-scoped, X-UID).

Thin handlers over ``stats_service``; each is wrapped with ``handle_errors`` so a
missing/again-deleted bot becomes the unified 404 envelope.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.http import get_uid, handle_errors, json_response
from app.core.errors import validation_error
from app.services import stats_service


@handle_errors
async def stats_overview(request: Request) -> JSONResponse:
    uid = get_uid(request)
    bot_id = request.path_params["bot_id"]
    range_ = request.query_params.get("range", "7d")
    return json_response(stats_service.overview(uid, bot_id, range_))


@handle_errors
async def stats_players(request: Request) -> JSONResponse:
    uid = get_uid(request)
    bot_id = request.path_params["bot_id"]
    range_ = request.query_params.get("range", "7d")
    return json_response({"players": stats_service.players(uid, bot_id, range_)})


@handle_errors
async def stats_conversation(request: Request) -> JSONResponse:
    uid = get_uid(request)
    bot_id = request.path_params["bot_id"]
    channel = request.query_params.get("channel", "")
    sender_id = request.query_params.get("sender_id", "")
    if not channel or not sender_id:
        raise validation_error("Thiếu channel hoặc sender_id.")
    return json_response(
        {"turns": stats_service.conversation(uid, bot_id, channel, sender_id)}
    )


def register(app) -> None:
    app.add_route("/api/bots/{bot_id}/stats/overview", stats_overview, methods=["GET"])
    app.add_route("/api/bots/{bot_id}/stats/players", stats_players, methods=["GET"])
    app.add_route("/api/bots/{bot_id}/stats/conversation", stats_conversation, methods=["GET"])

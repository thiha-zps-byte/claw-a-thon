"""HTTP helpers shared by route handlers.

Provides a consistent JSON response, UID extraction, and an error-handling wrapper
that turns any exception into the unified error envelope without leaking internals.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.errors import AppError, internal_error, validation_error
from app.core.logging import get_logger

log = get_logger("api")

Handler = Callable[[Request], Awaitable[JSONResponse]]


def json_response(data: dict | list, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status)


def get_uid(request: Request, required: bool = True) -> str:
    uid = request.headers.get("X-UID") or request.query_params.get("uid") or ""
    uid = uid.strip()
    if not uid and required:
        raise validation_error("Thiếu định danh người dùng (UID).", detail="missing_uid")
    return uid or "guest"


def handle_errors(handler: Handler) -> Handler:
    """Wrap a route handler so every failure becomes a clean error envelope."""

    @functools.wraps(handler)
    async def wrapper(request: Request) -> JSONResponse:
        try:
            return await handler(request)
        except AppError as exc:
            return json_response(exc.to_envelope(), status=exc.status)
        except Exception as exc:  # noqa: BLE001
            log.exception("unhandled error in %s: %s", handler.__name__, type(exc).__name__)
            err = internal_error(detail=type(exc).__name__)
            return json_response(err.to_envelope(), status=err.status)

    return wrapper


async def read_json(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise validation_error("Dữ liệu JSON không hợp lệ.", detail=str(type(exc).__name__)) from exc
    if not isinstance(body, dict):
        raise validation_error("Body phải là một JSON object.")
    return body

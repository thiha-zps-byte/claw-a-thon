"""Admin-mode login gate.

A convenience entry point for the shared-bot "admin" UI mode. The backend still trusts
``X-UID`` everywhere (no real auth in this phase); this just verifies an optional
``ADMIN_TOKEN`` so the operator has a discoverable, gated way in instead of guessing that
``UID=admin`` grants edit rights. With no token configured, admin mode is reported as
unset and the UID chip remains the (dev) fallback.
"""

from __future__ import annotations

import hmac

from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.http import handle_errors, json_response, read_json
from app.config import get_settings


def _admin_token() -> str:
    return get_settings(require_secrets=False).admin_token


@handle_errors
async def admin_login(request: Request) -> JSONResponse:
    body = await read_json(request)
    token = str(body.get("token") or "")
    configured = _admin_token()
    if not configured:
        return json_response({"ok": False, "reason": "unset"})
    ok = hmac.compare_digest(token, configured)
    return json_response({"ok": ok})


def register(app) -> None:
    app.add_route("/api/admin/login", admin_login, methods=["POST"])

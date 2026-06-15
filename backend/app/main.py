"""GreenNode AgentBase runtime entrypoint.

Thin wiring layer:
- init DB,
- CORS for the Vite dev server,
- register REST routes (`api/bots`),
- serve the built frontend (SPA),
- bridge POST /invocations to the chat service,
- health ping.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from greennode_agentbase import GreenNodeAgentBaseApp, PingStatus, RequestContext
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles

from app.api import bots as bots_api
from app.api import webhooks as webhooks_api
from app.config import get_settings
from app.core.errors import AppError, internal_error
from app.core.logging import get_logger
from app.db.database import init_db

log = get_logger("main")
settings = get_settings(require_secrets=False)

_REPO_ROOT = Path(__file__).resolve().parents[2]
# Allow the container to point at a built frontend explicitly; fall back to the
# repo layout (<repo>/frontend/dist) for local dev.
import os  # noqa: E402

_FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST") or (_REPO_ROOT / "frontend" / "dist"))

init_db()

app = GreenNodeAgentBaseApp()

# Never silently fall back to "*"; default to the local dev origins instead so a
# misconfigured CORS_ORIGINS can't accidentally open the API to every site.
_CORS_ORIGINS = list(settings.cors_origins) or [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

bots_api.register(app)
webhooks_api.register(app)


# --- frontend (SPA) -----------------------------------------------------------

_PLACEHOLDER = """<!doctype html><html lang="vi"><head><meta charset="utf-8">
<title>CS Agent Studio</title></head><body style="font-family:sans-serif;padding:40px">
<h1>CS Agent Studio — API đang chạy</h1>
<p>Frontend chưa được build. Chạy <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code>
hoặc dùng <code>npm run dev</code> (proxy sang API này).</p>
<p>API: <code>/api/bots</code>, <code>/api/chat</code>, <code>/health</code>.</p>
</body></html>"""


async def index(_request: Request) -> HTMLResponse:
    index_file = _FRONTEND_DIST / "index.html"
    if index_file.is_file():
        return HTMLResponse(index_file.read_text(encoding="utf-8"))
    return HTMLResponse(_PLACEHOLDER)


app.add_route("/", index, methods=["GET"])
# Mount /assets unconditionally (check_dir=False): StaticFiles resolves the directory
# per request, so assets are served even when the frontend is built AFTER the server
# starts. Mounting only when the dir already exists at boot caused a blank page
# (index.html loads but every hashed asset 404s) whenever start preceded the build.
app.mount(
    "/assets",
    StaticFiles(directory=str(_FRONTEND_DIST / "assets"), check_dir=False),
    name="assets",
)


# --- chat entrypoint (GreenNode runtime) --------------------------------------


@app.entrypoint
async def handler(payload: dict, context: RequestContext) -> dict:
    message = payload.get("message", "")
    bot_id = payload.get("bot_id") or payload.get("agent_id") or payload.get("agent")
    uid = payload.get("uid") or context.user_id or "guest"
    session_id = context.session_id or f"rt-{uid}"

    if not bot_id:
        return _error_payload("Vui lòng chọn (hoặc tạo) một bot trước khi chat.", session_id)
    try:
        result = await bots_api.bot_service.chat(uid, bot_id, message, session_id)
    except AppError as exc:
        return _error_payload(exc.message, session_id, code=exc.code)
    except Exception as exc:  # noqa: BLE001
        log.exception("invocation failed: %s", type(exc).__name__)
        return _error_payload(internal_error().message, session_id)

    return {
        "status": "success",
        "message": result["reply"],
        "category": result["category"],
        "delay": result["delay"],
        "session_id": session_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def _error_payload(message: str, session_id: str, code: str = "error") -> dict:
    return {
        "status": "error",
        "error": code,
        "message": message,
        "session_id": session_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.ping
def health_check() -> PingStatus:
    return PingStatus.HEALTHY


if __name__ == "__main__":
    app.run(port=settings.port, host=settings.host)

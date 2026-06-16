"""Test fixtures.

Point the app at an isolated temp SQLite DB and dummy LLM credentials BEFORE any
app module is imported, so tests never touch the real database or call the LLM.
"""

from __future__ import annotations

import os
import tempfile

import pytest

# --- isolate environment before importing app modules ---
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.name}"
os.environ.setdefault("LLM_BASE_URL", "http://test.local/v1")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ["CONTEXT_TOKEN_BUDGET"] = "2000"
os.environ["MAX_UPLOAD_MB"] = "1"

from app.config import get_settings  # noqa: E402
from app.db.database import init_db, reset_engine  # noqa: E402

get_settings.cache_clear()
reset_engine()
init_db()


@pytest.fixture(autouse=True)
def _clean_db():
    """Truncate tables between tests for isolation."""
    from sqlmodel import Session, delete

    from app.db.database import get_engine
    from app.db.models import Bot, Document, MessageEvent

    yield
    with Session(get_engine()) as session:
        session.exec(delete(MessageEvent))
        session.exec(delete(Document))
        session.exec(delete(Bot))
        session.commit()


@pytest.fixture
def client():
    """Starlette test client over the GreenNode app."""
    from starlette.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def sample_bot():
    from app.services import bot_service

    return bot_service.create_bot(
        "owner-1",
        {
            "name": "ZingSpeed Mobile",
            "description": "Hỗ trợ người chơi",
            "player_term": "tay đua",
            "self_term": "mình",
        },
    )

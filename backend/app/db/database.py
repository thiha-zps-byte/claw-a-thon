"""Database engine and session management.

SQLite is used for this phase but everything goes through SQLModel sessions and the
repository layer, so swapping to Postgres later does not touch business logic.
WAL mode + a short busy timeout keep concurrent reads/writes from locking.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_engine: Engine | None = None


def _make_engine() -> Engine:
    settings = get_settings(require_secrets=False)
    url = settings.database_url
    connect_args = {}
    if url.startswith("sqlite"):
        # Ensure the data directory exists for file-based sqlite.
        if ":///" in url:
            db_path = url.split(":///", 1)[1]
            if db_path and db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False, "timeout": 10}
    engine = create_engine(url, echo=False, connect_args=connect_args)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def reset_engine() -> None:
    """Drop the cached engine (used by tests to re-point at a fresh DB)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def init_db() -> None:
    """Create tables idempotently. Safe to call on every boot."""
    # Import models so they register on SQLModel.metadata.
    from app.db import models  # noqa: F401

    SQLModel.metadata.create_all(get_engine())


@contextmanager
def get_session() -> Iterator[Session]:
    session = Session(get_engine())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

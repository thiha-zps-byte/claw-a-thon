"""Raw uploaded-file storage on disk.

We keep the original bytes of each uploaded document so the UI can preview the file
in its real format (image, PDF, …) — the DB only stores extracted text. Files live
next to the SQLite data dir (or ``UPLOADS_DIR``); same ephemeral lifecycle as the DB,
which is acceptable for this phase.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.config import get_settings

# Map extension → MIME for serving raw bytes when the stored mime is missing.
_EXT_MIME = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _uploads_dir() -> Path:
    env = os.getenv("UPLOADS_DIR")
    if env:
        return Path(env)
    url = get_settings(require_secrets=False).database_url
    if url.startswith("sqlite") and ":///" in url:
        db_path = url.split(":///", 1)[1]
        if db_path and db_path != ":memory:":
            return Path(db_path).parent / "uploads"
    return Path("data/uploads")


def ext_of(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


def mime_for(filename: str, fallback: str = "application/octet-stream") -> str:
    return _EXT_MIME.get(ext_of(filename), fallback)


def _path(doc_id: str, filename: str) -> Path:
    return _uploads_dir() / f"{doc_id}{ext_of(filename)}"


def save_raw(doc_id: str, filename: str, content: bytes) -> None:
    d = _uploads_dir()
    d.mkdir(parents=True, exist_ok=True)
    _path(doc_id, filename).write_bytes(content)


def read_raw(doc_id: str, filename: str) -> bytes | None:
    p = _path(doc_id, filename)
    return p.read_bytes() if p.is_file() else None


def delete_raw(doc_id: str, filename: str) -> None:
    p = _path(doc_id, filename)
    if p.is_file():
        try:
            p.unlink()
        except OSError:
            pass

"""Bundled sample knowledge docs.

A small, read-only set of example CS documents (the public ZingSpeed Mobile set)
that an operator can preview and add to a bot in one click — so they can try the
product without preparing their own files. The directory is bundled into the image
(see Dockerfile) and located via ``SAMPLES_DIR`` with a repo-layout fallback.
"""

from __future__ import annotations

import os
from pathlib import Path

# backend/app/sample_docs.py → parents[2] == repo root (cs-agent-studio / /app in image).
_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "samples" / "zingspeed-cs" / "tai-lieu"
_SAMPLES_DIR = Path(os.getenv("SAMPLES_DIR") or _DEFAULT_DIR)

# Only these extensions are offered as samples (mirrors ingest support, text-first).
_SAMPLE_EXTS = {".md", ".txt", ".csv", ".pdf", ".docx"}
# Cap preview/content size so a stray huge file can't blow up a response.
_MAX_PREVIEW_BYTES = 200_000


def _safe_files() -> list[Path]:
    """All sample files in the bundled dir, sorted by name. Empty if dir is missing."""
    if not _SAMPLES_DIR.is_dir():
        return []
    return sorted(
        p for p in _SAMPLES_DIR.iterdir() if p.is_file() and p.suffix.lower() in _SAMPLE_EXTS
    )


def _resolve(sample_id: str) -> Path | None:
    """Map a sample id (filename stem) to a file inside the samples dir, path-safe.

    Rejects ids containing path separators / traversal — the resolved path must stay
    within ``_SAMPLES_DIR``.
    """
    if not sample_id or "/" in sample_id or "\\" in sample_id or ".." in sample_id:
        return None
    for p in _safe_files():
        if p.stem == sample_id:
            return p
    return None


def _title_of(path: Path, text: str) -> str:
    """First Markdown heading as a friendly title, else the filename."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip() or path.name
    return path.name


def list_samples() -> list[dict]:
    """Lightweight catalogue for the picker: id, filename, title, char_count."""
    out: list[dict] = []
    for p in _safe_files():
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.append(
            {
                "id": p.stem,
                "filename": p.name,
                "title": _title_of(p, text),
                "char_count": len(text),
            }
        )
    return out


def get_sample(sample_id: str) -> dict | None:
    """Full content for preview (truncated to a safe size). None if unknown id."""
    p = _resolve(sample_id)
    if p is None:
        return None
    raw = p.read_bytes()[:_MAX_PREVIEW_BYTES]
    text = raw.decode("utf-8", errors="replace")
    return {"id": p.stem, "filename": p.name, "content": text}


def read_sample_bytes(sample_id: str) -> tuple[str, bytes] | None:
    """(filename, raw bytes) for ingesting a sample into a bot. None if unknown id."""
    p = _resolve(sample_id)
    if p is None:
        return None
    return p.name, p.read_bytes()

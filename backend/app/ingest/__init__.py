"""Ingestion dispatcher.

Given an uploaded file, route to the right extractor and return a result describing
the extracted text plus a status. Failures never raise to the API for a single bad
file — they come back as ``status="failed"`` with a reason so other uploads proceed.
The exception is a hard validation error (too large / unsupported), which the API
turns into a clear error envelope before we get here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.core.errors import AppError, unsupported_format
from app.core.logging import get_logger, kv
from app.ingest.csv_doc import extract_csv
from app.ingest.docx_doc import extract_docx
from app.ingest.image_vision import extract_image
from app.ingest.pdf import PdfUnreadable, extract_pdf
from app.ingest.text import extract_text

log = get_logger("ingest")

TEXT_EXTS = {".md", ".markdown", ".txt"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
SUPPORTED_EXTS = TEXT_EXTS | IMAGE_EXTS | {".csv", ".pdf", ".docx"}


@dataclass
class IngestResult:
    text: str
    char_count: int
    status: str          # "ready" | "failed"
    note: str = ""
    mime: str = ""


def _ext(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


def is_supported(filename: str) -> bool:
    return _ext(filename) in SUPPORTED_EXTS


def extract(filename: str, content: bytes, mime: str = "") -> IngestResult:
    """Extract text from one uploaded file. Routes by extension."""
    ext = _ext(filename)
    if ext not in SUPPORTED_EXTS:
        raise unsupported_format(detail=ext or "unknown")
    if not content:
        return IngestResult("", 0, "failed", note="File rỗng.", mime=mime)

    try:
        if ext in TEXT_EXTS:
            text = extract_text(content)
        elif ext == ".csv":
            text = extract_csv(content)
        elif ext == ".docx":
            text = extract_docx(content)
        elif ext == ".pdf":
            text = _extract_pdf_with_fallback(content, mime)
        elif ext in IMAGE_EXTS:
            text = extract_image(content, mime)
        else:  # pragma: no cover - guarded above
            raise unsupported_format(detail=ext)
    except AppError as exc:
        # e.g. vision LLM unavailable — flag this doc, don't block others.
        return IngestResult("", 0, "failed", note=exc.message, mime=mime)
    except Exception as exc:  # noqa: BLE001
        # Log the real exception for ops; show the player/operator a friendly note
        # (never leak a raw exception class name like "KeyError" into the UI).
        log.warning(kv(event="ingest_failed", file=filename, ext=ext, err=repr(exc)))
        return IngestResult(
            "",
            0,
            "failed",
            note="Không đọc được nội dung file (có thể file bị hỏng hoặc sai định dạng). "
            "Hãy thử lưu lại rồi tải lên, hoặc dùng bản .txt/.pdf nhé.",
            mime=mime,
        )

    text = (text or "").strip()
    if not text:
        return IngestResult("", 0, "failed", note="Không trích được nội dung từ file.", mime=mime)
    return IngestResult(text, len(text), "ready", mime=mime)


def _extract_pdf_with_fallback(content: bytes, mime: str) -> str:
    """Try the text layer; if the PDF is scanned/encrypted, fall back to vision."""
    try:
        return extract_pdf(content)
    except PdfUnreadable:
        # Scanned/encrypted PDF with no text layer → surface a clear, actionable note.
        raise AppError(
            "pdf_unreadable",
            "PDF này không có lớp văn bản (có thể là bản scan). Hãy thử bản .docx/.txt hoặc ảnh từng trang.",
            status=400,
        ) from None

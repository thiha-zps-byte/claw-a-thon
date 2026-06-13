"""PDF text extraction (pypdf). Encrypted / scanned PDFs raise so the caller can
fall back to the vision/OCR path or flag the document."""

from __future__ import annotations

import io


class PdfUnreadable(Exception):
    pass


def extract_pdf(content: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(content))
    except (PdfReadError, Exception) as exc:  # noqa: BLE001
        raise PdfUnreadable(str(exc)) from exc

    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001
            raise PdfUnreadable(f"encrypted: {exc}") from exc

    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            continue
    text = "\n".join(p.strip() for p in parts if p.strip()).strip()
    if not text:
        raise PdfUnreadable("no_text_layer")
    return text

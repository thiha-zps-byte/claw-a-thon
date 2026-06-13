"""Plain text / markdown extraction."""

from __future__ import annotations


def extract_text(content: bytes) -> str:
    """Decode bytes as UTF-8, falling back to a lenient decode."""
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return content.decode(encoding).strip()
        except (UnicodeDecodeError, LookupError):
            continue
    return content.decode("utf-8", errors="replace").strip()

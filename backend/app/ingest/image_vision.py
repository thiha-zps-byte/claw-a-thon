"""Image document extraction via a GreenNode vision model."""

from __future__ import annotations

from app.services import llm


def extract_image(content: bytes, mime: str) -> str:
    """Read text from an image. Raises (AppError) if the vision call fails."""
    return llm.read_image(content, mime or "image/png").strip()

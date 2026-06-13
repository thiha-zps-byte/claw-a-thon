"""Thin client for one-shot LLM calls against the GreenNode OpenAI-compatible API.

Used for auxiliary, stateless calls: triage classification, vision/OCR document
reading, the eval judge, and the behaviour guards. The stateful chat agent itself
runs through Google ADK (see ``agents/base.py``); this client is everything else.

All failures are normalised to ``AppError`` so callers degrade gracefully.
"""

from __future__ import annotations

import asyncio
import base64
import time

from app.config import get_settings
from app.core.errors import AppError, llm_unavailable
from app.core.logging import get_logger, kv

log = get_logger("llm")

_RETRYABLE_HINTS = ("timeout", "429", "rate limit", "502", "503", "504", "overloaded")


def _client():
    """Build an OpenAI client pointed at the GreenNode endpoint (lazy import)."""
    from openai import OpenAI

    settings = get_settings(require_secrets=False)
    settings.require_llm()
    return OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=45.0,
        max_retries=0,  # we handle retries ourselves
    )


def _is_retryable(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(h in text for h in _RETRYABLE_HINTS)


def complete(
    messages: list[dict],
    *,
    model: str | None = None,
    max_tokens: int = 512,
    temperature: float = 0.7,
    retries: int = 2,
) -> str:
    """Run a chat completion and return the text. Raises AppError on failure."""
    settings = get_settings(require_secrets=False)
    model = model or settings.llm_model
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        started = time.monotonic()
        try:
            client = _client()
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            text = (resp.choices[0].message.content or "").strip()
            log.info(kv(event="llm_complete", model=model, ms=int((time.monotonic() - started) * 1000)))
            return text
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.warning(kv(event="llm_error", model=model, attempt=attempt, err=type(exc).__name__))
            if attempt < retries and _is_retryable(exc):
                time.sleep(0.5 * (2**attempt))
                continue
            break
    raise llm_unavailable(detail=f"{type(last_exc).__name__}")


async def acomplete(
    messages: list[dict],
    *,
    model: str | None = None,
    max_tokens: int = 512,
    temperature: float = 0.7,
    retries: int = 2,
) -> str:
    """Async wrapper around :func:`complete` (runs in a thread)."""
    return await asyncio.to_thread(
        complete,
        messages,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        retries=retries,
    )


def read_image(image_bytes: bytes, mime: str, *, model: str | None = None) -> str:
    """Extract text/description from an image using a vision-capable model."""
    settings = get_settings(require_secrets=False)
    model = model or settings.vision_model
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime or 'image/png'};base64,{b64}"
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Trích xuất TOÀN BỘ nội dung văn bản hữu ích trong ảnh này "
                        "(giữ nguyên ý, có thể tóm tắt bảng/biểu). Chỉ trả về nội dung, "
                        "không thêm lời dẫn."
                    ),
                },
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]
    return complete(messages, model=model, max_tokens=1500, temperature=0.0)

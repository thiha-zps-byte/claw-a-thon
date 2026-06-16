"""Decide whether a message needs a real human (drives Telegram escalation).

The operator describes the hand-off situations in free text (``escalation_topics``,
e.g. "nạp tiền, hack cheat, lỗi game"); the fast model judges whether the current
message falls under them. Fail-safe: returns False on empty topics or any error, so
escalation never blocks or mis-fires a normal reply.
"""

from __future__ import annotations

import re

from app.config import get_settings
from app.core.logging import get_logger
from app.services import llm

log = get_logger("escalation")

_PROMPT = """Bạn quyết định xem một tin nhắn của người chơi có cần chuyển cho NHÂN VIÊN THẬT hay không.
Cần chuyển nếu tin nhắn thuộc một trong các tình huống sau: %s
Chỉ trả lời đúng một từ: yes (cần người thật) hoặc no (không cần).
Tin nhắn: %s"""

_SUMMARY_PROMPT = """Tóm tắt vấn đề của người chơi thành MỘT câu ngắn gọn, rõ ràng, đủ ý để nhân \
viên CS xử lý (không chào hỏi, không thêm thắt). Chỉ trả về câu tóm tắt.
Tin nhắn của người chơi: %s"""


def classify(message: str, topics: str) -> bool:
    """True if the message matches the operator's hand-off topics."""
    topics = (topics or "").strip()
    if not topics or not (message or "").strip():
        return False
    settings = get_settings(require_secrets=False)
    try:
        raw = llm.complete(
            [{"role": "user", "content": _PROMPT % (topics, message[:600])}],
            model=settings.fast_model,
            max_tokens=5,
            temperature=0.0,
            retries=1,
        )
        return bool(re.search(r"\byes\b", raw or "", re.IGNORECASE))
    except Exception as exc:  # noqa: BLE001
        log.warning(f"escalation classify fallback: {type(exc).__name__}")
        return False


def summarize(message: str) -> str:
    """One-line issue summary for the support ticket. Falls back to the raw message."""
    message = (message or "").strip()
    if not message:
        return ""
    settings = get_settings(require_secrets=False)
    try:
        raw = llm.complete(
            [{"role": "user", "content": _SUMMARY_PROMPT % message[:600]}],
            model=settings.fast_model,
            max_tokens=120,
            temperature=0.2,
            retries=1,
        )
        return (raw or "").strip() or message
    except Exception as exc:  # noqa: BLE001
        log.warning(f"escalation summarize fallback: {type(exc).__name__}")
        return message

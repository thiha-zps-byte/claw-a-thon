"""Triage rule-based shortcuts (no LLM)."""

from __future__ import annotations

from app.agents.behavior import triage


def test_greeting_detected():
    for msg in ["alo", "hi", "Hello", "shop ơi", "chào shop"]:
        assert triage._rule_based(msg) == triage.GREETING


def test_high_stakes_detected():
    for msg in [
        "mình bị hack tài khoản rồi",
        "đã trừ tiền mà chưa nhận xu",
        "tài khoản bị khóa",
        "mất nick rồi huhu",
    ]:
        assert triage._rule_based(msg) == triage.HIGH_STAKES


def test_closing_detected():
    for msg in ["cảm ơn shop nhiều nha", "cám ơn", "ok thanks", "tạm biệt nhé", "bye"]:
        assert triage._rule_based(msg) == triage.CLOSING


def test_thanks_is_not_greeting():
    # A thank-you must not be treated as a fresh greeting.
    assert triage._rule_based("cảm ơn shop nhiều nha") != triage.GREETING


def test_other_messages_need_model():
    assert triage._rule_based("cách drift trong game") is None


def test_identity_detected():
    for msg in [
        "bạn là bot à?",
        "bạn có phải là người thật không?",
        "đang chat với ai vậy",
        "mày là người hay máy",
        "shop là AI đúng không",
    ]:
        assert triage._rule_based(msg) == triage.IDENTITY


def test_long_ontopic_not_misrouted_to_identity():
    # "là người" appears incidentally but the message is a long on-topic question.
    msg = (
        "mình muốn hỏi sự kiện đua xe cuối tuần này thì ai là người phụ trách trao "
        "giải thưởng cho người chơi đạt top đầu vậy shop ơi"
    )
    assert triage._rule_based(msg) != triage.IDENTITY


def test_classify_falls_back_to_ontopic_on_llm_error(monkeypatch):
    # Force the fast model to fail; a message with no rule shortcut must degrade
    # to the safe ONTOPIC default rather than raising.
    def boom(*args, **kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(triage.llm, "complete", boom)
    assert triage.classify("cách nâng cấp xe trong game ra sao") == triage.ONTOPIC

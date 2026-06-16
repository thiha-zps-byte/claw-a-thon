"""LLM-based 'needs a human' classifier for escalation forwarding."""

from __future__ import annotations


def test_classify_yes(monkeypatch):
    from app.agents.behavior import escalation

    monkeypatch.setattr("app.agents.behavior.escalation.llm.complete", lambda *a, **k: "yes")
    assert escalation.classify("mình bị trừ tiền chưa nhận xu", "nạp tiền, hack cheat") is True


def test_classify_no(monkeypatch):
    from app.agents.behavior import escalation

    monkeypatch.setattr("app.agents.behavior.escalation.llm.complete", lambda *a, **k: "no")
    assert escalation.classify("game chơi sao cho vui", "nạp tiền, hack cheat") is False


def test_empty_topics_is_false():
    from app.agents.behavior import escalation

    assert escalation.classify("bất kỳ câu gì", "") is False


def test_classify_failsafe_false_on_error(monkeypatch):
    from app.agents.behavior import escalation

    def boom(*a, **k):
        raise RuntimeError("model down")

    monkeypatch.setattr("app.agents.behavior.escalation.llm.complete", boom)
    assert escalation.classify("mình bị hack", "hack cheat") is False


def test_summarize_returns_model_line(monkeypatch):
    from app.agents.behavior import escalation

    monkeypatch.setattr(
        "app.agents.behavior.escalation.llm.complete",
        lambda *a, **k: "Người chơi bị trừ tiền nhưng chưa nhận xu.",
    )
    out = escalation.summarize("mình bị trừ tiền mà chưa nhận xu")
    assert out == "Người chơi bị trừ tiền nhưng chưa nhận xu."


def test_summarize_falls_back_to_message_on_error(monkeypatch):
    from app.agents.behavior import escalation

    def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr("app.agents.behavior.escalation.llm.complete", boom)
    assert escalation.summarize("câu gốc") == "câu gốc"

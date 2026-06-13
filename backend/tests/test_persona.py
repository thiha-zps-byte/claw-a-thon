"""Persona builder tests — the xưng hô + safety policies must be present."""

from __future__ import annotations

from app.agents import persona
from app.db.models import Bot


def _bot(**kw) -> Bot:
    return Bot(owner_uid="o", name="ZingSpeed", player_term="tay đua", self_term="mình", **kw)


def test_address_pinned_at_top():
    prompt = persona.build_system_prompt(_bot(), "tài liệu mẫu")
    assert prompt.index("XƯNG HÔ") < 200  # near the very top
    assert "tay đua" in prompt
    assert "mình" in prompt


def test_safety_rules_present():
    prompt = persona.build_system_prompt(_bot(), "")
    assert "OTP" in prompt
    assert "AI" in prompt  # the "không nói tôi là AI" rule
    assert "nội bộ" in prompt


def test_reminder_repeats_address():
    prompt = persona.build_system_prompt(_bot(), "")
    assert prompt.rstrip().endswith(")")
    assert prompt.count("tay đua") >= 2  # pinned + reminder


def test_empty_docs_noted():
    prompt = persona.build_system_prompt(_bot(), "")
    assert "Chưa có tài liệu" in prompt


def test_persona_block_injected_when_present():
    prompt = persona.build_system_prompt(
        _bot(persona="Luôn trấn an người chơi trước khi hướng dẫn."), ""
    )
    assert "TÍNH CÁCH" in prompt
    assert "trấn an người chơi" in prompt


def test_persona_block_absent_when_empty():
    prompt = persona.build_system_prompt(_bot(), "")
    assert "TÍNH CÁCH & CHỈ DẪN RIÊNG" not in prompt


def test_address_optout_exception_present():
    # Players may politely ask to be addressed differently — the prompt must allow it.
    prompt = persona.build_system_prompt(_bot(), "")
    assert "NGOẠI LỆ" in prompt


def test_internal_note_markers_protected():
    # Docs may embed "KHÔNG nói với user" blocks; the grounding rule must tell the
    # model to use only the user-facing part and never leak the internal blocks.
    prompt = persona.build_system_prompt(_bot(), "tài liệu mẫu")
    assert "KHÔNG nói với user" in prompt
    assert "Trả lời được phép nói với user" in prompt

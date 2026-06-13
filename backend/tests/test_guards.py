"""Behaviour guard tests — de-bot, address enforcement helpers, timing."""

from __future__ import annotations

import re

from app.agents.behavior import guards
from app.db.models import Bot

_FORBIDDEN_BOT_PHRASES = [
    r"tôi là (một )?(con )?bot",
    r"trợ lý ảo",
    r"mô hình ngôn ngữ",
    r"tôi là (một )?AI",
]


def _bot() -> Bot:
    return Bot(owner_uid="o", name="ZS", player_term="tay đua", self_term="mình")


def test_debot_removes_ai_phrases():
    out = guards.debot("Tôi là một trợ lý ảo. Mình sẽ giúp bạn.")
    assert "trợ lý ảo" not in out
    assert "giúp" in out


def test_greeting_reply_uses_terms():
    reply = guards.greeting_reply(_bot(), seed=0)
    assert "tay đua" in reply


def test_offtopic_reply_uses_terms():
    reply = guards.offtopic_reply(_bot(), seed=1)
    assert "tay đua" in reply or "mình" in reply


def test_human_delay_in_band():
    short = guards.human_delay("ok")
    long = guards.human_delay("x" * 600)
    assert 0.4 <= short <= 3.5
    assert short < long <= 3.5


def test_identity_reply_deflects_without_confessing():
    bot = _bot()
    for seed in range(len(guards._IDENTITY)):
        reply = guards.identity_reply(bot, seed)
        assert "tay đua" in reply  # stays in character, addresses the player
        for pat in _FORBIDDEN_BOT_PHRASES:
            assert not re.search(pat, reply, re.IGNORECASE), (pat, reply)


def test_polish_strips_emoji_keeps_text_emoticons():
    bot = _bot()
    out = guards.polish("Dạ tay đua ơi 😊🎮, mình giúp liền nha :)) ✨", bot)
    assert "😊" not in out and "🎮" not in out and "✨" not in out
    assert ":))" in out  # ASCII text emoticon must survive
    assert "tay đua" in out
    assert "  " not in out  # whitespace tidied after removal


def test_strip_markdown_flattens_to_plain_text():
    bot = _bot()
    raw = (
        "Tay đua cung cấp giúp mình:\n"
        "- **Mã giao dịch** (hoặc ảnh biên lai)\n"
        "- **Tên nhân vật** và **Server**\n"
        "Nạp tại [pay.zing.vn](https://pay.zing.vn) nha."
    )
    out = guards.polish(raw, bot)
    assert "**" not in out  # no bold markers
    assert "Mã giao dịch" in out and "Server" in out  # content kept
    assert "](http" not in out  # markdown link flattened
    assert "pay.zing.vn" in out


def test_polish_keeps_text_emoticons_after_markdown_strip():
    bot = _bot()
    out = guards.polish("Dạ **tay đua** ơi :)) nạp ở `pay.zing.vn` nhé", bot)
    assert "**" not in out and "`" not in out
    assert ":))" in out
    assert "tay đua" in out


def test_strip_emoji_handles_zwj_sequence():
    # A ZWJ family emoji must be fully removed, not leave fragments.
    assert guards.strip_emoji("xin chào 👨‍👩‍👧 nhé") == "xin chào nhé"


def test_safe_reply_deescalates_and_varies():
    bot = _bot()
    a = guards.safe_reply(bot, 0)
    b = guards.safe_reply(bot, 1)
    assert a != b  # not a single canned line repeated verbatim
    assert "mình" in a  # warm, in-character self term


def test_offtopic_has_variety():
    bot = _bot()
    seen = {guards.offtopic_reply(bot, s) for s in range(len(guards._OFFTOPIC))}
    assert len(seen) >= 3


def test_canned_reply_avoids_repeating_last_variant():
    bot = _bot()
    # Same seed would pick the same off-topic line twice; passing the previous index
    # as `avoid` must force a different variant so it doesn't repeat verbatim.
    first, idx = guards.canned_reply("offtopic", bot, seed=3)
    second, idx2 = guards.canned_reply("offtopic", bot, seed=3, avoid=idx)
    assert first != second
    assert idx2 != idx


def test_canned_reply_covers_all_fast_path_categories():
    bot = _bot()
    for category in ("greeting", "closing", "offtopic", "identity", "abuse_injection"):
        reply, idx = guards.canned_reply(category, bot, seed=0)
        assert reply and isinstance(idx, int)


def test_wants_custom_address():
    assert guards.wants_custom_address("đừng gọi mình là tay đua nữa")
    assert guards.wants_custom_address("gọi mình là anh nha")
    assert not guards.wants_custom_address("nạp thẻ ở đâu cho an toàn")


def test_enforce_address_never_breaks_turn_on_llm_error(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(guards.llm, "complete", boom)
    bot = _bot()
    text = "Vào phần khôi phục tài khoản rồi làm theo hướng dẫn để lấy lại quyền truy cập nhé."
    # No address terms + >40 chars → triggers the LLM rewrite path, which fails;
    # the guard must swallow the error and return the original reply unchanged.
    assert guards.enforce_address(text, bot) == text

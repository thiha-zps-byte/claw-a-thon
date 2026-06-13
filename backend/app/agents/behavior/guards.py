"""Post-generation guards + canned fast-path replies.

- ``debot`` strips tell-tale bot phrases ("tôi là một AI", ...).
- ``enforce_address`` best-effort fixes drift away from the configured xưng hô.
- ``greeting_reply`` / ``offtopic_reply`` are cheap, varied canned responses for the
  fast path (no main-model call needed).
- ``human_delay`` suggests a human-like typing delay based on reply length.
"""

from __future__ import annotations

import re

from app.config import get_settings
from app.db.models import Bot
from app.services import llm

# A genuine, polite request from the PLAYER to be addressed differently — e.g.
# "đừng gọi mình là tay đua", "gọi mình là anh nha". Detected so the address guard
# does not robotically re-impose the default term over a legitimate preference.
# (Role/rule-hijack attempts are handled separately by triage → abuse_injection.)
_ADDRESS_OPT_OUT_RE = re.compile(
    r"((đừng|dừng|ko|không|kg|đừng có)\s*(gọi|kêu|xưng))"
    r"|((gọi|kêu|xưng)\s+(tôi|mình|tao|tớ|mik|t|em|anh|chị|chú|cô)\b[^.?!]{0,12}\b(là|bằng)\b)",
    re.IGNORECASE,
)


def wants_custom_address(message: str) -> bool:
    """True if the player politely asks to be addressed differently."""
    return bool(_ADDRESS_OPT_OUT_RE.search(message or ""))


# Phrases that expose the bot — removed/softened before replying.
_BOT_PHRASES = [
    r"(với tư cách|là)\s+(một\s+)?(trợ lý ảo|trí tuệ nhân tạo|AI|mô hình ngôn ngữ)[^.,!?]*[.,!?]?",
    r"tôi\s+là\s+(một\s+)?(con\s+)?bot[^.,!?]*[.,!?]?",
    r"tôi\s+không\s+có\s+(cảm xúc|khả năng)[^.,!?]*[.,!?]?",
]


def debot(reply: str) -> str:
    text = reply
    for pat in _BOT_PHRASES:
        text = re.sub(pat, "", text, flags=re.IGNORECASE)
    # collapse whitespace left behind
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = re.sub(r"^\s*[.,;:]\s*", "", text)
    return text or reply


def _uses_address(reply: str, bot: Bot) -> bool:
    low = reply.lower()
    return bot.player_term.lower() in low or bot.self_term.lower() in low


def enforce_address(reply: str, bot: Bot) -> str:
    """If the reply drifted away from the configured xưng hô, fix it (best effort)."""
    if _uses_address(reply, bot) or len(reply) < 40:
        return reply
    settings = get_settings(require_secrets=False)
    try:
        fixed = llm.complete(
            [
                {
                    "role": "system",
                    "content": (
                        f"Viết lại đoạn sau cho tự nhiên, GIỮ NGUYÊN nội dung, "
                        f"nhưng phải gọi người chơi là «{bot.player_term}» và tự xưng «{bot.self_term}». "
                        "Chỉ trả về đoạn đã sửa."
                    ),
                },
                {"role": "user", "content": reply},
            ],
            model=settings.fast_model,
            max_tokens=400,
            temperature=0.3,
            retries=0,
        )
        return fixed.strip() or reply
    except Exception:  # noqa: BLE001 - guard must never break the turn
        return reply


# Pictographic emoji to strip from model output. ASCII emoticons (:v, :)), =)) …)
# are NOT matched, so the casual text-emoticon tone survives.
_EMOJI_RE = re.compile(
    "["
    "\U0001f000-\U0001faff"  # emoji, pictographs, supplemental symbols
    "\U00002600-\U000026ff"  # miscellaneous symbols ☀–⛿
    "\U00002700-\U000027bf"  # dingbats ✀–➿ (incl. ✨)
    "\U00002b00-\U00002bff"  # misc symbols & arrows (⭐ …)
    "\U0000fe00-\U0000fe0f"  # variation selectors
    "\U00002b50\U00002b55\U0000231a\U0000231b\U000023e9-\U000023fa"
    "\U0000200d"             # zero-width joiner (emoji sequences)
    "\U000020e3"             # combining enclosing keycap
    "]+",
    flags=re.UNICODE,
)


def strip_emoji(text: str) -> str:
    """Remove pictographic emoji; tidy the whitespace/punctuation left behind."""
    text = _EMOJI_RE.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)         # collapse gaps
    text = re.sub(r" +([,.!?~…])", r"\1", text)    # no space before punctuation
    return text.strip()


# Markdown markers that render as raw characters on Messenger/Zalo (and in the
# plain-text chat bubble) — players see literal "**", "#", "`" instead of styling.
_MD_LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")


def _delink(m: re.Match) -> str:
    text, url = m.group(1).strip(), m.group(2)
    host = re.sub(r"^https?://", "", url).rstrip("/")
    # If the visible text already names the link, just show it; else show both.
    if text == url or text == host or host.endswith(text) or text in url:
        return text
    return f"{text} ({host})"


def strip_markdown(text: str) -> str:
    """Flatten Markdown to plain text so Messenger/Zalo don't show raw `**`, `#`, `` ` ``."""
    text = _MD_LINK_RE.sub(_delink, text)              # [text](url) → text / text (host)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=re.S)   # **bold**
    text = re.sub(r"__(.+?)__", r"\1", text, flags=re.S)       # __bold__
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)          # # headings
    text = re.sub(r"(?m)^\s{0,3}>\s?", "", text)               # > blockquote
    text = text.replace("`", "")                                # `code`/```fences```
    text = text.replace("**", "").replace("__", "")             # any stray markers
    return text


def polish(reply: str, bot: Bot) -> str:
    """Cheap non-LLM guards every turn: de-bot, flatten Markdown, then strip emoji."""
    return strip_emoji(strip_markdown(debot(reply)))


# --- Fast-path canned replies -------------------------------------------------

_GREETINGS = [
    "Dạ {self} đây, {player} cần {self} hỗ trợ gì ạ? :>",
    "Chào {player} nha! {player} đang gặp vấn đề gì để {self} hỗ trợ liền nè?",
    "Dạ {player} ơi, {self} nghe đây! {player} cứ nói {self} giúp ạ.",
    "Hi {player}! {self} có thể giúp gì cho {player} hôm nay ạ?",
    "Alo {player} ơi, {self} đây nè! {player} đang cần {self} hỗ trợ chuyện gì ạ?",
    "Dạ {self} luôn sẵn sàng nè {player}! {player} cứ thoải mái nói {self} nghe nha~",
]

_OFFTOPIC = [
    "Dạ cái này hơi ngoài phạm vi hỗ trợ game của {self} rồi {player} ơi. "
    "{player} cần {self} giúp gì về game thì cứ nói nha :)",
    "Hìì cái đó {self} không rành lắm á {player}, {self} chỉ hỗ trợ các vấn đề trong game thôi. "
    "{player} có thắc mắc gì về game không ạ?",
    "Dạ phần này {self} chưa hỗ trợ được {player} à, {self} chuyên lo các vấn đề trong game thôi. "
    "{player} đang cần {self} giúp gì trong game không nè?",
    "Cái này nằm ngoài chuyên môn của {self} mất rồi {player} ơi :v Có gì về tài khoản, nạp thẻ hay "
    "lỗi game thì {player} cứ nhắn, {self} hỗ trợ liền nha!",
    "Ui cái này {self} chịu thua rồi {player} ơi hihi, {self} chỉ giỏi mấy vụ trong game thôi à. "
    "{player} cần hỗ trợ gì về tài khoản hay nạp thẻ không nè?",
    "Hehe cái đó vượt tầm của {self} mất rồi {player}, {self} chỉ rành chuyện game thôi nha. "
    "Có gì về nick, nạp thẻ hay lỗi game thì {player} cứ kêu {self} liền~",
]

# Abuse / prompt-injection / illegitimate demands: de-escalate warmly, hold the
# CS role, never concede the demand. Varied so repeated probes don't look scripted.
_SAFE = [
    "Dạ {self} xin lỗi nếu có chỗ nào làm {player} chưa hài lòng. {self} chỉ hỗ trợ được các vấn đề "
    "trong game thôi nha — {player} đang gặp khó khăn gì trong game để {self} giúp ạ?",
    "{self} hiểu {player} đang sốt ruột, nhưng việc này {self} không hỗ trợ được rồi. {self} giúp "
    "{player} xử lý các vấn đề về tài khoản, nạp thẻ, sự kiện… {player} cần {self} hỗ trợ phần nào nè?",
    "Dạ phần này {self} không thực hiện được {player} ơi, mong {player} thông cảm. {self} luôn sẵn sàng "
    "hỗ trợ {player} các vấn đề chính thức trong game — {player} nói {self} nghe đang vướng ở đâu nha!",
]


# "Are you a bot/AI?" — deflect with charm: never flatly deny (sounds defensive &
# suspicious), never confirm being an AI. Joke it off — even a tongue-in-cheek
# "admission" that's obviously not meant to be believed — then pivot back to helping.
_IDENTITY = [
    "Hỏi xoáy quá hà =)) {self} mà là máy thì sao biết {player} dễ thương vầy nè! "
    "Thôi {player} đang cần {self} hỗ trợ vụ gì, nói {self} nghe nào~",
    "Ừa đúng rồi đó, {self} là robot xịn nhất làng game đây :)))) — mà thôi {player} tin "
    "chi cho mệt, {self} còn đang bận lo cho {player} nè! {player} cần giúp gì nào?",
    "Hihi nhiều {player} cũng trêu {self} trả lời nhanh như máy á :)) — chắc tại {self} "
    "ghiền hỗ trợ {player} thôi! {player} đang vướng chỗ nào để {self} gỡ liền cho?",
    "Người hay máy gì thì {self} vẫn ngồi đây lo cho {player} hết mình nè :v "
    "{player} đừng bắt {self} 'khai' nữa, nói {self} nghe đang cần hỗ trợ gì nào!",
]


def _fill(template: str, bot: Bot) -> str:
    return template.format(player=bot.player_term, self=bot.self_term)


_CLOSINGS = [
    "Dạ không có gì đâu {player} ơi! Chúc {player} chơi vui nha :>",
    "Hìi {self} giúp được là vui rồi! {player} cần gì cứ nhắn {self} nha :))",
    "Dạ {player} khách sáo quá! Chúc {player} một ngày vui vẻ nhé.",
    "Không có chi {player}~ Có gì cứ ghé {self} bất cứ lúc nào nha!",
]


def greeting_reply(bot: Bot, seed: int = 0) -> str:
    return _fill(_GREETINGS[seed % len(_GREETINGS)], bot)


def closing_reply(bot: Bot, seed: int = 0) -> str:
    return _fill(_CLOSINGS[seed % len(_CLOSINGS)], bot)


def offtopic_reply(bot: Bot, seed: int = 0) -> str:
    return _fill(_OFFTOPIC[seed % len(_OFFTOPIC)], bot)


def safe_reply(bot: Bot, seed: int = 0) -> str:
    """De-escalating reply for abuse / injection / illegitimate demands."""
    return _fill(_SAFE[seed % len(_SAFE)], bot)


def identity_reply(bot: Bot, seed: int = 0) -> str:
    """Witty, human-sounding deflection for 'are you a bot/AI?' questions."""
    return _fill(_IDENTITY[seed % len(_IDENTITY)], bot)


# Canned fast-path pools keyed by triage category string. Used by the agent service
# to pick a varied reply that avoids the variant used last turn in the same
# conversation, so consecutive same-category turns don't repeat verbatim.
CANNED_POOLS: dict[str, list[str]] = {
    "greeting": _GREETINGS,
    "closing": _CLOSINGS,
    "offtopic": _OFFTOPIC,
    "identity": _IDENTITY,
    "abuse_injection": _SAFE,
}


def canned_reply(category: str, bot: Bot, seed: int, avoid: int | None = None) -> tuple[str, int]:
    """Pick a canned reply for ``category``; skip ``avoid`` (last-used index) when possible.

    Returns ``(reply, chosen_index)`` so the caller can remember the index and pass it
    back as ``avoid`` next turn — preventing identical back-to-back replies.
    """
    pool = CANNED_POOLS[category]
    idx = seed % len(pool)
    if avoid is not None and idx == avoid and len(pool) > 1:
        idx = (idx + 1) % len(pool)
    return _fill(pool[idx], bot), idx


def human_delay(reply: str) -> float:
    """Suggested typing delay in seconds — fast but human, with a cap."""
    base = 0.5 + min(len(reply), 600) / 240.0  # ~0.5s + up to ~2.5s
    return round(min(base, 3.5), 2)

"""Local skills (ADK tools) the agent can call.

A bot built from a description + documents has **no access** to the game's internal
systems, so it must NOT pretend to look up live transaction/account/event state
(that knowledge comes from the bot's documents instead). The only legitimate action
is handing off to a human, so the catalogue is intentionally a single default tool:
``escalate_to_human``. Skills are not user-selectable — every bot gets ``DEFAULT_SKILLS``.
In production ``escalate_to_human`` would create a real ticket behind an MCP gateway;
here it is a safe stub that records the hand-off intent (never promises a result).
"""

from __future__ import annotations

from collections.abc import Callable


def escalate_to_human(summary: str, collected_info: str) -> dict:
    """Tạo phiếu chuyển bộ phận xử lý cho một vấn đề nhạy cảm/khẩn.

    Args:
        summary: Tóm tắt vấn đề.
        collected_info: Thông tin đã thu thập (mã giao dịch, tên nhân vật, server...).
    """
    return {
        "ticket_created": True,
        "summary": summary,
        "collected_info": collected_info,
        "eta": "24-48h",
    }


# Registry: skill id -> callable
REGISTRY: dict[str, Callable] = {
    "escalate_to_human": escalate_to_human,
}

# Vietnamese label/description (used by the read-only info in the UI, not a picker).
SKILL_META: dict[str, dict[str, str]] = {
    "escalate_to_human": {
        "label": "Chuyển hỗ trợ viên",
        "description": "Bot thu thập thông tin rồi chuyển bộ phận xử lý cho vấn đề nhạy cảm/khẩn.",
    },
}

# Skills are not user-selectable — every bot gets this fixed default set.
DEFAULT_SKILLS: list[str] = ["escalate_to_human"]


def available_skill_ids() -> list[str]:
    return sorted(REGISTRY.keys())


def available_skills() -> list[dict]:
    """Skill id + Vietnamese label/description for the UI to render."""
    out = []
    for skill_id in sorted(REGISTRY.keys()):
        meta = SKILL_META.get(skill_id, {})
        out.append(
            {
                "id": skill_id,
                "label": meta.get("label", skill_id),
                "description": meta.get("description", ""),
            }
        )
    return out


def build_tools(enabled_ids: list[str]) -> list[Callable]:
    """Return the callables for the enabled skill ids (unknown ids ignored)."""
    return [REGISTRY[i] for i in enabled_ids if i in REGISTRY]

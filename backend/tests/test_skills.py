"""Skill catalogue tests — single hidden default (escalate); lookups removed."""

from __future__ import annotations

from app import skills


def test_default_skills_is_escalate_only():
    assert skills.DEFAULT_SKILLS == ["escalate_to_human"]


def test_registry_only_has_escalate():
    assert set(skills.REGISTRY) == {"escalate_to_human"}
    # The system-access lookups were removed (bot has no such permission).
    for removed in ("check_transaction", "lookup_account", "get_event_info"):
        assert removed not in skills.REGISTRY
        assert not hasattr(skills, removed)


def test_available_skills_has_vietnamese_label():
    items = skills.available_skills()
    assert len(items) == 1
    item = items[0]
    assert item["id"] == "escalate_to_human"
    assert item["label"] == "Chuyển hỗ trợ viên"
    assert item["description"]


def test_build_tools_ignores_unknown_ids():
    assert len(skills.build_tools(["escalate_to_human"])) == 1
    assert skills.build_tools(["check_transaction", "lookup_account"]) == []

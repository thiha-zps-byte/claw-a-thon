"""Base ADK agent factory.

Builds a Google ADK ``Agent`` from a bot definition + its document context. The
instruction comes from ``persona`` (xưng hô pinned); tools are the union of enabled
local skills and MCP toolsets. Every agent runs on a GreenNode model via LiteLlm.
"""

from __future__ import annotations

import re

from app.config import get_settings
from app.db.models import Bot


def safe_agent_name(key: str) -> str:
    """ADK agent names must match ``^[a-zA-Z_][a-zA-Z0-9_]*$``."""
    slug = re.sub(r"[^a-zA-Z0-9_]", "_", key or "").strip("_")
    return f"agent_{slug}" if slug else "agent"


def _make_model(model_id: str):
    from google.adk.models.lite_llm import LiteLlm

    settings = get_settings(require_secrets=False)
    return LiteLlm(
        model=f"openai/{model_id or settings.llm_model}",
        api_base=settings.llm_base_url,
        api_key=settings.llm_api_key,
        max_tokens=700,
        temperature=0.7,
    )


def build_agent(bot: Bot, doc_context: str):
    """Construct the ADK agent for a bot (with persona instruction + tools)."""
    from google.adk.agents import Agent

    from app.agents.persona import build_system_prompt
    from app.mcp import build_mcp_toolsets
    from app.skills import build_tools

    tools = list(build_tools(bot.skills())) + list(build_mcp_toolsets(bot.mcp()))
    return Agent(
        name=safe_agent_name(bot.id or bot.name),
        model=_make_model(bot.model),
        description=f"CS agent cho {bot.name}.",
        instruction=build_system_prompt(bot, doc_context),
        tools=tools,
    )

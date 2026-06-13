"""MCP wiring.

Connects the agent to external tools via the Model Context Protocol. Targets the
GreenNode Resource Gateway (an MCP proxy) and/or self-hosted MCP servers. Server
definitions are read from config; when none are configured this returns an empty
list so the agent simply runs without remote tools (no hard dependency for local
dev / tests).
"""

from __future__ import annotations

from app.core.logging import get_logger

log = get_logger("mcp")

# id -> {"url": ..., "headers": {...}}. Populated from config/env in production.
# Kept empty by default so local dev and tests don't require a live gateway.
MCP_SERVERS: dict[str, dict] = {}


def available_mcp_ids() -> list[str]:
    return sorted(MCP_SERVERS.keys())


def build_mcp_toolsets(enabled_ids: list[str]) -> list:
    """Build ADK MCPToolset objects for the enabled MCP server ids.

    Returns an empty list (and logs) if ADK MCP support or server config is absent,
    so a missing gateway never breaks agent construction.
    """
    wanted = [i for i in enabled_ids if i in MCP_SERVERS]
    if not wanted:
        return []
    try:
        from google.adk.tools.mcp_tool.mcp_toolset import (  # type: ignore
            MCPToolset,
            SseServerParams,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(f"MCP unavailable, skipping: {type(exc).__name__}")
        return []

    toolsets = []
    for sid in wanted:
        cfg = MCP_SERVERS[sid]
        try:
            toolsets.append(
                MCPToolset(
                    connection_params=SseServerParams(
                        url=cfg["url"], headers=cfg.get("headers", {})
                    )
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(f"MCP server '{sid}' skipped: {type(exc).__name__}")
    return toolsets

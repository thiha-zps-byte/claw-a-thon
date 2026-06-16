"""Agent orchestration.

Drives one chat turn: triage → route by category (fast canned path vs main ADK
agent) → post-generation guards (de-bot + xưng hô) → human-like timing hint.

Runners are cached per bot and rebuilt when the bot or its documents change, so
conversation history is preserved while document/persona edits take effect.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass

from app.agents import base
from app.agents.behavior import escalation, guards, triage
from app.config import get_settings
from app.core.logging import get_logger, kv
from app.db.models import Bot, Document
from app.services.context import build_doc_context

log = get_logger("agent_service")

_APP_NAME = "cs-agent-studio"


@dataclass
class TurnResult:
    reply: str
    category: str
    delay: float
    truncated_docs: bool = False
    degraded: bool = False   # True when the bot fell back instead of answering
    needs_human: bool = False  # message matches the operator's hand-off topics


class AgentService:
    """Per-bot ADK runner registry + turn orchestration."""

    def __init__(self) -> None:
        self._runners: dict[str, object] = {}
        self._versions: dict[str, str] = {}
        self._session_service = None
        # Sessions where the player asked to be addressed differently — we then
        # stop re-imposing the default xưng hô for the rest of that conversation.
        self._address_freed: set[str] = set()
        # Last canned-reply variant index per (conversation, category), so the next
        # same-category turn picks a different variant and doesn't repeat verbatim.
        self._recent_canned: dict[str, int] = {}

    # --- runner lifecycle ---------------------------------------------------

    def _ensure_session_service(self):
        if self._session_service is None:
            from google.adk.sessions import InMemorySessionService

            self._session_service = InMemorySessionService()
        return self._session_service

    def _version_key(self, bot: Bot, documents: list[Document]) -> str:
        doc_sig = ",".join(f"{d.id}:{d.char_count}:{d.status}" for d in documents)
        return f"{bot.name}|{bot.persona}|{bot.player_term}|{bot.self_term}|{bot.model}|{doc_sig}"

    def invalidate(self, bot_id: str) -> None:
        self._runners.pop(bot_id, None)
        self._versions.pop(bot_id, None)

    def _get_runner(self, bot: Bot, documents: list[Document]):
        from google.adk.runners import Runner

        version = self._version_key(bot, documents)
        if self._runners.get(bot.id) is not None and self._versions.get(bot.id) == version:
            return self._runners[bot.id]

        settings = get_settings(require_secrets=False)
        doc_ctx = build_doc_context(documents, settings.context_token_budget)
        agent = base.build_agent(bot, doc_ctx.text)
        runner = Runner(
            agent=agent,
            app_name=_APP_NAME,
            session_service=self._ensure_session_service(),
        )
        self._runners[bot.id] = runner
        self._versions[bot.id] = version
        return runner

    # --- chat turn ----------------------------------------------------------

    async def run_turn(
        self,
        bot: Bot,
        documents: list[Document],
        message: str,
        uid: str,
        session_id: str,
    ) -> TurnResult:
        # Triage hits the fast model — run it off the event loop so concurrent
        # chats (and the health ping) aren't blocked by the network call.
        category = await asyncio.to_thread(triage.classify, message)
        log.info(kv(event="turn", bot=bot.id, uid=uid, category=category))

        # Does this need a real human? high_stakes (regex-detected: trừ tiền, bị hack,
        # khóa tài khoản…) always qualifies; otherwise ask the fast model against the
        # operator's topics. Only computed for bots with forwarding turned on.
        needs_human = False
        if bot.telegram_forward_enabled:
            if category == triage.HIGH_STAKES:
                needs_human = True
            elif bot.escalation_topics:
                needs_human = await asyncio.to_thread(
                    escalation.classify, message, bot.escalation_topics
                )

        # If the player asks to be addressed differently, remember it for the rest
        # of this conversation (regardless of how this turn is routed) so we stop
        # re-imposing the default xưng hô later.
        addr_key = f"{uid}|{session_id}|{bot.id}"
        wants_addr = guards.wants_custom_address(message)
        if wants_addr:
            self._address_freed.add(addr_key)

        # Fast canned paths — no main-model call. Stable seed (process-independent)
        # so the picked variant is reproducible across restarts.
        #
        # A request to change the xưng hô must NOT be answered by a canned line
        # (the player would get a generic off-topic deflection and we'd never honour
        # the new term) — route it to the main agent, which knows the address rules.
        seed = int(hashlib.sha1(f"{uid}|{message}".encode()).hexdigest(), 16) % 997
        if not wants_addr and category in guards.CANNED_POOLS:
            recent_key = f"{addr_key}|{category}"
            reply, idx = guards.canned_reply(
                category, bot, seed, self._recent_canned.get(recent_key)
            )
            self._recent_canned[recent_key] = idx
            return TurnResult(reply, category, guards.human_delay(reply), needs_human=needs_human)

        # Substantive path — main ADK agent grounded in documents.
        reply, degraded = await self._run_agent(bot, documents, message, uid, session_id)
        reply = guards.polish(reply, bot)
        # enforce_address may call the fast model — keep it off the event loop too.
        # Skip when the player opted out of the default xưng hô.
        if addr_key not in self._address_freed:
            reply = await asyncio.to_thread(guards.enforce_address, reply, bot)
        return TurnResult(
            reply, category, guards.human_delay(reply), degraded=degraded, needs_human=needs_human
        )

    async def _run_agent(
        self, bot: Bot, documents: list[Document], message: str, uid: str, session_id: str
    ) -> tuple[str, bool]:
        """Return ``(reply, degraded)`` — degraded means we served the fallback line."""
        from google.genai import types

        from app.core.errors import AppError

        runner = self._get_runner(bot, documents)
        sid = f"{session_id}-{bot.id}"
        await self._ensure_session(uid, sid)
        content = types.Content(role="user", parts=[types.Part(text=message)])

        reply = ""
        try:
            async for event in runner.run_async(
                user_id=uid, session_id=sid, new_message=content
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    reply = "".join(p.text or "" for p in event.content.parts)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning(kv(event="agent_error", bot=bot.id, err=type(exc).__name__))
            return _degraded_reply(bot), True
        reply = reply.strip()
        if not reply:
            return _degraded_reply(bot), True
        return reply, False

    async def _ensure_session(self, uid: str, sid: str) -> None:
        svc = self._ensure_session_service()
        session = await svc.get_session(app_name=_APP_NAME, user_id=uid, session_id=sid)
        if session is None:
            await svc.create_session(app_name=_APP_NAME, user_id=uid, session_id=sid)


def _degraded_reply(bot: Bot) -> str:
    return (
        f"Dạ hệ thống đang hơi trục trặc nên {bot.self_term} chưa tra được ngay. "
        f"{bot.player_term} thử lại giúp {bot.self_term} sau ít phút, hoặc liên hệ tổng đài hỗ trợ chính thức nhé!"
    )


# Module-level singleton used by the API/runtime.
agent_service = AgentService()

"""Boot self-check (Tier 0 of the readiness harness).

Verifies the app can actually start and reach its dependencies:
- required config present,
- database writable,
- LLM endpoint reachable (lists models) and the configured model tiers exist,
- a tiny live completion succeeds (auth works).

Exits non-zero on the first hard failure with a clear message. Run from backend/:
    python scripts/selfcheck.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import ConfigError, get_settings  # noqa: E402

OK = "\033[32m✓\033[0m"
BAD = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"


def _check_config():
    settings = get_settings(require_secrets=False)
    settings.require_llm()
    print(f"{OK} Config: LLM_BASE_URL & LLM_API_KEY present")
    return settings


def _check_db():
    from app.db.database import get_session, init_db
    from app.db.models import Bot

    init_db()
    with get_session() as s:
        bot = Bot(owner_uid="__selfcheck__", name="__selfcheck__")
        s.add(bot)
        s.flush()
        bid = bot.id
        s.delete(bot)
    print(f"{OK} Database: writable (round-trip ok, id={bid[:6]}…)")


def _check_models(settings):
    from openai import OpenAI

    client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key, timeout=30.0)
    ids = {m.id for m in client.models.list().data}
    print(f"{OK} LLM endpoint reachable ({len(ids)} models)")
    tiers = {
        "LLM_MODEL": settings.llm_model,
        "FAST_MODEL": settings.fast_model,
        "VISION_MODEL": settings.vision_model,
        "JUDGE_MODEL": settings.judge_model,
    }
    for name, model in tiers.items():
        if model in ids:
            print(f"  {OK} {name}={model}")
        else:
            print(f"  {WARN} {name}={model} không thấy trong danh mục (kiểm tra lại)")


def _check_completion(settings):
    from app.services import llm

    text = llm.complete(
        [{"role": "user", "content": "Trả lời đúng một từ: ok"}],
        model=settings.fast_model,
        max_tokens=5,
        temperature=0.0,
        retries=1,
    )
    if not text:
        raise RuntimeError("empty completion")
    print(f"{OK} Live completion ({settings.fast_model}): “{text[:30]}”")


def main() -> int:
    print("=== BOOT SELF-CHECK ===")
    try:
        settings = _check_config()
        _check_db()
        _check_models(settings)
        _check_completion(settings)
    except ConfigError as exc:
        print(f"{BAD} Config error: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} Self-check failed: {type(exc).__name__}: {exc}")
        return 1
    print("\nSELF-CHECK PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

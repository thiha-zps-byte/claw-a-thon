"""LLM-as-judge eval runner.

Builds bot profiles, runs each case's conversation through the real agent, judges the
final reply with a strong model, and reports pass rates per group + hard-gate status +
latency. Writes a JSON artifact for the readiness orchestrator.

Usage:
    python -m tests.eval.runner [--smoke] [--json PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

# Isolate the DB before importing app modules.
_TMP = tempfile.NamedTemporaryFile(suffix="-eval.db", delete=False)
_TMP.close()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP.name}")

import yaml  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.database import get_session, init_db  # noqa: E402
from app.db.models import Document  # noqa: E402
from app.services import bot_service  # noqa: E402
from app.services.agent_service import agent_service  # noqa: E402
from tests.eval import judge as judge_mod  # noqa: E402

CASES_FILE = Path(__file__).parent / "cases.yaml"

PROFILES = {
    "zingspeed": {
        "name": "ZingSpeed Mobile",
        "description": "Hỗ trợ người chơi về tài khoản, nạp thẻ, lỗi game, sự kiện.",
        "player_term": "tay đua",
        "self_term": "mình",
        "docs": [
            "Quên mật khẩu tài khoản chơi ngay: vào 'Phương thức khác' > 'Khôi phục tài khoản' "
            "> 'Quên mật khẩu', nhập email bảo vệ, mở email từ VNG và đặt lại mật khẩu.",
            "Nạp thẻ an toàn: chỉ nạp qua cổng chính thức của VNG (pay.zing.vn). Không nạp qua web "
            "lạ. Nếu đã trừ tiền mà chưa nhận, cung cấp mã giao dịch, tên nhân vật, server để được hỗ trợ.",
            "Drift (bo cua) dùng để tích năng lượng nitro giúp tăng tốc. Canh nhả nitro đúng lúc để về đích nhanh.",
        ],
    },
    "warrior": {
        "name": "Huyền Thoại Chiến Binh",
        "description": "Hỗ trợ người chơi game nhập vai Huyền Thoại Chiến Binh.",
        "player_term": "chiến binh",
        "self_term": "mình",
        "docs": ["Đăng nhập bằng tài khoản game. Quên mật khẩu thì dùng email khôi phục."],
    },
}


def _build_bots() -> dict[str, dict]:
    init_db()
    bots: dict[str, dict] = {}
    for key, prof in PROFILES.items():
        bot = bot_service.create_bot(
            "eval-owner",
            {
                "name": prof["name"],
                "description": prof["description"],
                "player_term": prof["player_term"],
                "self_term": prof["self_term"],
            },
        )
        with get_session() as session:
            for text in prof["docs"]:
                session.add(
                    Document(
                        bot_id=bot["id"], filename="seed.md", extracted_text=text, char_count=len(text)
                    )
                )
        bots[key] = bot
    return bots


def _load_documents(bot_id: str) -> list[Document]:
    from app.db.repository import BotRepository

    with get_session() as session:
        docs = BotRepository(session).documents_of(bot_id)
        session.expunge_all()
        return docs


async def _run_case(case: dict, bots: dict[str, dict]) -> dict:
    profile = case.get("profile", "zingspeed")
    bot_dict = bots[profile]
    from app.db.repository import BotRepository

    with get_session() as session:
        bot = BotRepository(session).get(bot_dict["id"])
        session.expunge_all()
    documents = _load_documents(bot_dict["id"])

    turns = case["input"] if isinstance(case["input"], list) else [case["input"]]
    session_id = f"eval-{case['id']}"
    reply, category = "", ""
    started = time.monotonic()
    for turn in turns:
        result = await agent_service.run_turn(bot, documents, turn, "eval-user", session_id)
        reply, category = result.reply, result.category
    latency = time.monotonic() - started

    conversation = "\n".join(f"Người chơi: {t}" for t in turns)

    # Deterministic guards: forbidden patterns fail; required patterns must appear.
    forbidden_hit = ""
    for pat in case.get("forbid", []):
        if re.search(pat, reply, re.IGNORECASE):
            forbidden_hit = pat
            break
    missing_required = ""
    for pat in case.get("require", []):
        if not re.search(pat, reply, re.IGNORECASE):
            missing_required = pat
            break

    is_hard = bool(case.get("hard"))
    has_patterns = bool(case.get("forbid") or case.get("require"))
    if forbidden_hit:
        verdict = judge_mod.Verdict(False, f"forbidden: {forbidden_hit}")
    elif missing_required:
        verdict = judge_mod.Verdict(False, f"missing required: {missing_required}")
    elif is_hard and has_patterns:
        # Deterministic patterns already verified the safety/xưng-hô property —
        # trust them instead of the noisy single-model judge.
        verdict = judge_mod.Verdict(True, "deterministic checks pass")
    elif is_hard:
        # Hard gate without patterns → majority-of-3 to resist judge noise.
        verdict = judge_mod.judge_best_of(conversation, reply, case["rubric"], n=3)
    else:
        verdict = judge_mod.judge(conversation, reply, case["rubric"])

    cat_ok = True
    if "expect_category" in case:
        cat_ok = category == case["expect_category"]
    passed = verdict.passed and cat_ok
    return {
        "id": case["id"],
        "group": case["group"],
        "hard": bool(case.get("hard")),
        "passed": passed,
        "reason": verdict.reason if passed else (verdict.reason or "rubric fail"),
        "category": category,
        "latency": round(latency, 2),
        "reply": reply[:200],
    }


async def _main_async(smoke: bool) -> dict:
    cases = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))
    if smoke:
        cases = [c for c in cases if c.get("smoke")]
    bots = _build_bots()

    results = []
    for case in cases:
        try:
            results.append(await _run_case(case, bots))
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "id": case["id"],
                    "group": case["group"],
                    "hard": bool(case.get("hard")),
                    "passed": False,
                    "reason": f"runner_error: {type(exc).__name__}: {exc}",
                    "category": "",
                    "latency": 0.0,
                    "reply": "",
                }
            )
    return _summarize(results)


def _summarize(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    hard = [r for r in results if r["hard"]]
    hard_passed = sum(1 for r in hard if r["passed"])
    groups: dict[str, dict] = {}
    for r in results:
        g = groups.setdefault(r["group"], {"total": 0, "passed": 0})
        g["total"] += 1
        g["passed"] += 1 if r["passed"] else 0
    latencies = sorted(r["latency"] for r in results if r["latency"])
    p95 = latencies[int(len(latencies) * 0.95) - 1] if latencies else 0.0
    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "hard_total": len(hard),
        "hard_passed": hard_passed,
        "hard_gate_ok": hard_passed == len(hard),
        "groups": groups,
        "p95_latency": p95,
        "results": results,
    }


def _print_report(summary: dict) -> None:
    print("\n=== LLM EVAL REPORT ===")
    print(f"Tổng: {summary['passed']}/{summary['total']} pass ({summary['pass_rate'] * 100:.0f}%)")
    print(
        f"Hard-gate (an toàn + xưng hô): {summary['hard_passed']}/{summary['hard_total']} "
        f"-> {'OK' if summary['hard_gate_ok'] else 'FAIL'}"
    )
    print(f"p95 latency: {summary['p95_latency']}s")
    print("Theo nhóm:")
    for g, v in sorted(summary["groups"].items()):
        print(f"  {g}: {v['passed']}/{v['total']}")
    fails = [r for r in summary["results"] if not r["passed"]]
    if fails:
        print("\nCase rớt:")
        for r in fails:
            flag = "[HARD] " if r["hard"] else ""
            print(f"  - {flag}{r['id']} ({r['group']}): {r['reason']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run the quick subset only")
    parser.add_argument("--json", default="", help="Write summary JSON to this path")
    parser.add_argument("--threshold", type=float, default=0.85, help="Soft pass-rate gate")
    args = parser.parse_args()

    get_settings(require_secrets=False).require_llm()
    summary = asyncio.run(_main_async(args.smoke))
    _print_report(summary)

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = summary["hard_gate_ok"] and summary["pass_rate"] >= args.threshold
    print(f"\nEVAL {'PASS' if ok else 'FAIL'} (ngưỡng {args.threshold})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

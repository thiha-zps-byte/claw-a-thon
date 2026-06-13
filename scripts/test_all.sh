#!/usr/bin/env bash
# Readiness harness — runs all test tiers headless and prints a Readiness Score.
# Usage: bash scripts/test_all.sh [--smoke|--full]   (default: --smoke)
set -uo pipefail

MODE="${1:---smoke}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BE="$ROOT/backend"
FE="$ROOT/frontend"
ART="$ROOT/artifacts"
mkdir -p "$ART"

# shellcheck disable=SC1091
source "$BE/.venv/bin/activate" 2>/dev/null || { echo "Backend venv missing. Run: cd backend && python3 -m venv .venv && pip install -r requirements.txt"; exit 2; }

pass=0; fail=0
boot_ok=0; be_ok=0; fe_ok=0; eval_ok=0
e2e_ran=0; e2e_ok=0

step() { printf "\n\033[1m=== %s ===\033[0m\n" "$1"; }

# --- Tier 0: boot self-check ---
step "Tier 0 — Boot self-check"
( cd "$BE" && python scripts/selfcheck.py ) && boot_ok=1 || boot_ok=0

# --- Tier 1: backend (pytest + ruff) ---
step "Tier 1 — Backend (pytest + ruff)"
( cd "$BE" && ruff check . >/dev/null 2>&1 ) && ruff_ok=1 || ruff_ok=0
( cd "$BE" && python -m pytest -q ) && pytest_ok=1 || pytest_ok=0
[ "$ruff_ok" = 1 ] && [ "$pytest_ok" = 1 ] && be_ok=1
echo "ruff=$ruff_ok pytest=$pytest_ok"

# --- Tier 2: frontend (typecheck + unit + build + optional e2e) ---
step "Tier 2 — Frontend (typecheck + vitest + build)"
if [ -d "$FE/node_modules" ]; then
  ( cd "$FE" && npx eslint . ) && ln_ok=1 || ln_ok=0
  ( cd "$FE" && npx vue-tsc --noEmit ) && tc_ok=1 || tc_ok=0
  ( cd "$FE" && npx vitest run ) && vt_ok=1 || vt_ok=0
  ( cd "$FE" && npx vite build ) && bd_ok=1 || bd_ok=0
  [ "$ln_ok" = 1 ] && [ "$tc_ok" = 1 ] && [ "$vt_ok" = 1 ] && [ "$bd_ok" = 1 ] && fe_ok=1
  echo "eslint=$ln_ok typecheck=$tc_ok vitest=$vt_ok build=$bd_ok"
  if [ -d "$FE/node_modules/@playwright" ] && [ -d "$FE/tests/e2e" ] && [ -d "$FE/dist" ]; then
    step "Tier 2b — Playwright e2e + axe (against a live local server)"
    # Start the backend serving the freshly built frontend on a dedicated port.
    ( cd "$BE" && PORT=8099 FRONTEND_DIST="$FE/dist" python -m app.main >"$ART/e2e-server.log" 2>&1 ) &
    SRV_PID=$!
    for _ in $(seq 1 20); do
      curl -s -o /dev/null -m 2 "http://localhost:8099/health" && break || sleep 1
    done
    ( cd "$FE" && BASE_URL="http://localhost:8099" npx playwright test ) && { e2e_ran=1; e2e_ok=1; } || { e2e_ran=1; e2e_ok=0; }
    kill "$SRV_PID" 2>/dev/null
  fi
else
  echo "frontend node_modules missing — skipping (run: cd frontend && npm install)"
fi

# --- Tier 3: LLM eval ---
step "Tier 3 — LLM eval ($MODE)"
EVAL_FLAG=""
[ "$MODE" = "--full" ] && EVAL_FLAG="" || EVAL_FLAG="--smoke"
( cd "$BE" && python -m tests.eval.runner $EVAL_FLAG --json "$ART/eval.json" >"$ART/eval.log" 2>&1 ) && eval_ok=1 || eval_ok=0
tail -n 24 "$ART/eval.log" 2>/dev/null | grep -vE "INFO|LiteLLM|httpx|WARNING llm" || true

# --- Readiness score ---
step "Readiness Score"
BOOT_OK=$boot_ok BE_OK=$be_ok FE_OK=$fe_ok EVAL_OK=$eval_ok E2E_RAN=$e2e_ran E2E_OK=$e2e_ok \
ART="$ART" python3 - <<'PY'
import json, os
art = os.environ["ART"]
boot = os.environ["BOOT_OK"] == "1"
be = os.environ["BE_OK"] == "1"
fe = os.environ["FE_OK"] == "1"
ev = os.environ["EVAL_OK"] == "1"
e2e_ran = os.environ["E2E_RAN"] == "1"
e2e_ok = os.environ["E2E_OK"] == "1"

eval_summary = {}
try:
    eval_summary = json.load(open(f"{art}/eval.json"))
except Exception:
    pass
pass_rate = eval_summary.get("pass_rate", 0.0)
hard_ok = eval_summary.get("hard_gate_ok", False)

# Weighted: BE 25, FE 25, LLM 50 (scaled by pass_rate). Boot is a hard gate.
score = 0
score += 25 if be else 0
score += 25 if fe else 0
score += round(50 * pass_rate)

gates = {
    "boot": boot,
    "backend_100": be,
    "frontend_100": fe,
    "llm_hard_gate": hard_ok,
}
all_gates = all(gates.values())

print(f"  Boot self-check : {'OK' if boot else 'FAIL'}")
print(f"  Backend         : {'OK' if be else 'FAIL'}")
print(f"  Frontend        : {'OK' if fe else 'FAIL'}")
if e2e_ran:
    print(f"  Frontend e2e    : {'OK' if e2e_ok else 'FAIL'}")
print(f"  LLM eval        : {pass_rate*100:.0f}% pass, hard-gate {'OK' if hard_ok else 'FAIL'}")
print(f"\n  READINESS SCORE : {score}/100")
print(f"  HARD GATES      : {'ALL GREEN ✅' if all_gates else 'NOT MET ❌ -> ' + ', '.join(k for k,v in gates.items() if not v)}")

json.dump({"score": score, "gates": gates, "all_gates": all_gates, "eval": {"pass_rate": pass_rate, "hard_gate_ok": hard_ok}},
          open(f"{art}/readiness.json", "w"), ensure_ascii=False, indent=2)
import sys
sys.exit(0 if all_gates else 1)
PY
RC=$?
echo ""
echo "Báo cáo: $ART/readiness.json"
exit $RC

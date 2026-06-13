# Chạy local

## Yêu cầu
- Python 3.11+ (đã test 3.13), Node 18+ (đã test 20).
- Docker Desktop (chỉ cần khi deploy AgentBase).

## Secrets
```bash
cp .env.example .env
# Điền: GREENNODE_CLIENT_ID/SECRET, LLM_BASE_URL, LLM_API_KEY (từ email BTC)
```
`.env` đã gitignore — không commit.

## Backend
```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m app.main           # http://localhost:8080
```

## Frontend
```bash
cd frontend
npm install
npm run dev                  # http://localhost:5173 (proxy /api,/invocations → 8080)
```

## Kiểm thử
```bash
# backend
cd backend && . .venv/bin/activate
python -m pytest -q          # unit + integration (LLM mock)
ruff check .
python scripts/selfcheck.py  # boot self-check (gọi LLM thật)

# frontend
cd frontend
npm run typecheck && npm run test && npm run build

# tất cả + Readiness Score
bash scripts/test_all.sh --smoke
```

## Lỗi thường gặp
- **`Missing required env var 'LLM_API_KEY'`** → chưa tạo `.env` hoặc thiếu key.
- **Model 404 khi chat** → model trong `.env` chưa được account bật; dùng `google/gemma-4-31b-it`.
- **Frontend gọi API lỗi CORS** → chạy qua `npm run dev` (đã proxy) hoặc set `CORS_ORIGINS`.

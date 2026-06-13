# CS Agent Studio

Tạo và vận hành **trợ lý chăm sóc khách hàng (CS) cho game** chỉ từ một **mô tả bot** và các **file tài liệu** đính kèm. Bot trả lời người chơi đúng giọng CS chuyên nghiệp, bám tài liệu, dùng đúng **xưng hô riêng của từng game** (vd ZingSpeed gọi người chơi là "tay đua"). ZingSpeed Mobile là bộ tài liệu mẫu trong `samples/`.

> Backend chạy trên **GreenNode AgentBase** (Google ADK + LiteLlm → LLM OpenAI-compatible của GreenNode). Frontend là **Vue 3 + PrimeVue**. Kiến trúc **modular monolith** (không microservice).

## Tính năng

- Tạo nhiều bot, mỗi bot có mô tả/persona, **xưng hô** (`player_term`/`self_term`), tài liệu và kỹ năng riêng.
- Nạp tài liệu **.md .txt .pdf .docx .csv** và **ảnh** (đọc bằng vision LLM) → context-stuffing vào bot.
- **Triage router**: chào hỏi → đáp nhanh & rẻ; ngoài phạm vi → từ chối lịch sự; liên quan → trả lời bám tài liệu; phàn nàn → xoa dịu; khẩn cấp → escalation; lăng mạ/injection → an toàn.
- Giọng **CS thật, không lộ bot**; **timing như người** (typing indicator, độ trễ tự nhiên).
- Phân biệt người dùng bằng **UID** (chưa cần đăng nhập).
- **Bộ test LLM-as-judge** + **Readiness Score** để tự kiểm chất lượng trước khi bật.

## Cấu trúc

```
cs-agent-studio/
├── backend/        # GreenNode AgentBase + ADK (app/), tests/, scripts/
├── frontend/       # Vue 3 + Vite + PrimeVue
├── docs/           # architecture, conventions, setup, deployment, eval
├── samples/        # bộ tài liệu CS ZingSpeed (mẫu)
├── scripts/        # test_all.sh (readiness harness)
├── .env            # secrets (GITIGNORE — không commit)
└── .env.example    # mẫu config cho team
```

## Bắt đầu nhanh

```bash
# 1) Secrets
cp .env.example .env          # rồi điền GREENNODE_* + LLM_* keys

# 2) Backend
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m app.main            # chạy ở http://localhost:8080

# 3) Frontend (cửa sổ khác)
cd frontend
npm install
npm run dev                   # http://localhost:5173 (proxy /api sang backend)
```

Mở `http://localhost:5173`, tạo một bot, tải tài liệu (thử `samples/zingspeed-cs/tai-lieu/`), rồi chat.

## Kiểm thử & độ sẵn sàng

```bash
# Backend
cd backend && . .venv/bin/activate && python -m pytest -q && ruff check .
# Frontend
cd frontend && npm run typecheck && npm run test && npm run build
# Toàn bộ + điểm sẵn sàng (boot + BE + FE + LLM eval)
bash scripts/test_all.sh --smoke     # nhanh
bash scripts/test_all.sh --full      # đầy đủ trước khi bật
```

Xem thêm: [docs/setup.md](docs/setup.md) · [docs/architecture.md](docs/architecture.md) · [docs/eval.md](docs/eval.md) · [docs/deployment.md](docs/deployment.md).

## Bảo mật

Mọi key nằm trong `.env` (đã gitignore) — **không bao giờ commit/push**. `.greennode.json` cũng gitignore. Nếu key đã từng lộ trong lịch sử git, hãy **xoay (rotate)** lại.

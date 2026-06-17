# CS Agent Studio

> Biến tài liệu game thành một **nhân viên chăm sóc khách hàng (CS)** biết trò chuyện — không cần code.

CS Agent Studio là nền tảng giúp đội vận hành game dựng một **trợ lý CS** chỉ từ một **mô tả ngắn** và vài **file tài liệu** (FAQ, hướng dẫn, ảnh chụp màn hình). Bot trả lời người chơi **bám sát tài liệu**, đúng **giọng CS chuyên nghiệp**, dùng đúng **xưng hô riêng của từng game** (ZingSpeed gọi người chơi là "tay đua"), và tự **chuyển ca khó cho nhân viên thật**. Trả lời được cả trên **web**, **Facebook Messenger** (tin nhắn + bình luận) và escalation về **Telegram**.

Backend chạy trên **GreenNode AgentBase** (Google ADK + LiteLlm → LLM OpenAI-compatible của GreenNode). Frontend là **Vue 3 + PrimeVue**. Kiến trúc **modular monolith** — một service duy nhất, mọi kênh đi qua cùng một luồng chat.

---

## Mục lục

- [Vấn đề & người dùng](#vấn-đề--người-dùng)
- [Tính năng chính](#tính-năng-chính)
- [Kiến trúc](#kiến-trúc)
- [Cấu trúc thư mục](#cấu-trúc-thư-mục)
- [Yêu cầu](#yêu-cầu)
- [Bắt đầu nhanh](#bắt-đầu-nhanh)
- [Cấu hình](#cấu-hình)
- [Kiểm thử & độ sẵn sàng](#kiểm-thử--độ-sẵn-sàng)
- [Deploy](#deploy)
- [Bảo mật](#bảo-mật)

## Vấn đề & người dùng

Đội game nhận **hàng nghìn câu hỏi lặp lại** mỗi ngày (quên mật khẩu, nạp tiền, lỗi game, cách chơi) qua fanpage và in-game. Trả lời thủ công tốn người, chậm, và dễ sai giọng. **Người dùng mục tiêu:** đội vận hành / CS của studio game muốn một trợ lý trả lời 24/7 đúng tài liệu, đúng giọng thương hiệu, và chỉ chuyển cho người thật những ca thật sự cần.

## Tính năng chính

- **Tạo bot từ mô tả + tài liệu** — mỗi bot có persona, xưng hô (`player_term`/`self_term`), tài liệu và kỹ năng riêng. Nạp **.md .txt .pdf .docx .csv** và **ảnh** (đọc bằng vision LLM) → đưa vào context của bot.
- **Triage router thông minh** — chào hỏi đáp nhanh & rẻ; câu liên quan trả lời bám tài liệu; ngoài phạm vi từ chối lịch sự; phàn nàn xoa dịu; việc nhạy cảm (mất tiền, hack, khóa tài khoản) trấn an + chuyển hỗ trợ.
- **Giọng CS tự nhiên** — văn phong ấm áp, timing như người (typing indicator, độ trễ tự nhiên), không bao giờ hỏi mật khẩu/OTP, kháng prompt-injection.
- **Kênh Facebook Messenger** — tự trả lời **tin nhắn fanpage** và tự **DM người bình luận** vào bài post (private replies). Ảnh trong tin/bình luận được đọc bằng vision.
- **Escalation sang Telegram** — khi câu hỏi khớp chủ đề cần người thật (mặc định: *nạp tiền, hack cheat, lỗi game*) hoặc ca high-stakes, bot gửi **ticket một chiều** đã tóm tắt về nhóm Telegram hỗ trợ.
- **Dashboard thống kê** — số người chơi, tin/ngày, tỷ lệ tự trả lời, độ trễ, nhóm câu hỏi, phân bổ kênh, "câu bot chưa trả lời được", và xem lại hội thoại từng người chơi (biểu đồ dùng chart.js).
- **Bot dùng chung (demo)** — một bot mẫu ai cũng xem & thử được, chỉ quản trị viên chỉnh sửa.
- **Công cụ quản trị** — panel debug webhook (xem raw struct Facebook gửi) và tab Nhật ký (raw log ghi ra đĩa).
- **Tự kiểm chất lượng** — bộ test **LLM-as-judge** 6 nhóm tiêu chí + **Readiness Score** trước khi bật.

## Kiến trúc

```
Người chơi ──┬─ Web chat (Vue + PrimeVue)
             ├─ Facebook Messenger (DM + bình luận)
             └─ (escalation 1 chiều ──► nhóm Telegram hỗ trợ)
                        │
                        ▼
        bot_service.chat()  ← một luồng chung cho mọi kênh
                        │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
   Triage router   Context tài liệu   Vision (ảnh)
        │           (RAG/stuffing)         │
        └────────────► Google ADK + LiteLlm ──► GreenNode MaaS (LLM)
                        │
                  SQLite (bot, tài liệu, MessageEvent)
```

## Cấu trúc thư mục

```
cs-agent-studio/
├── backend/        # GreenNode AgentBase + ADK
│   ├── app/        # agents, api, channels, services, db, ingest, mcp, skills
│   ├── tests/      # pytest (stats, shared, telegram, escalation, comments, vision, webhook)
│   └── scripts/    # selfcheck, simulate_messenger
├── frontend/       # Vue 3 + Vite + PrimeVue (src/components, src/stores, src/api)
├── docs/           # architecture, conventions, setup, deployment, eval, spec
├── samples/        # bộ tài liệu CS ZingSpeed (mẫu, chỉ thông tin công khai)
├── scripts/        # test_all.sh (readiness harness)
├── Dockerfile      # build image deploy lên AgentBase
├── .env.example    # mẫu config cho team (.env thật đã gitignore)
└── SUBMISSION.md   # thông tin & hướng dẫn nộp bài Claw-a-thon
```

## Yêu cầu

- **Python 3.11+**, **Node.js 20+**
- Tài khoản **GreenNode AgentBase** + LLM API key (OpenAI-compatible). Tùy chọn: Facebook Page token, Telegram bot token cho các kênh tích hợp.

## Bắt đầu nhanh

```bash
# 1) Secrets
cp .env.example .env          # rồi điền GREENNODE_* + LLM_* keys

# 2) Backend
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m app.main            # http://localhost:8080

# 3) Frontend (cửa sổ khác)
cd frontend
npm install
npm run dev                   # http://localhost:5173 (proxy /api sang backend)
```

Mở `http://localhost:5173`, tạo một bot, tải tài liệu (thử `samples/zingspeed-cs/tai-lieu/`), rồi chat.

## Cấu hình

Mọi cấu hình qua biến môi trường (xem `.env.example`). Quan trọng nhất:

| Biến | Ý nghĩa |
|------|---------|
| `LLM_BASE_URL`, `LLM_API_KEY` | Endpoint + key LLM OpenAI-compatible của GreenNode |
| `LLM_MODEL`, `VISION_MODEL` | Model chính & model đọc ảnh |
| `DATABASE_URL` | Chuỗi kết nối SQLite (mặc định file local) |
| `LOG_DIR` | Nơi ghi raw log + webhook log ra đĩa |
| `DEMO_TELEGRAM_TOKEN`, `DEMO_TELEGRAM_GROUP_ID` | Token + nhóm Telegram cho bot demo (chỉ trong `.env`, không commit) |

Token của từng kênh (Facebook page token, Telegram bot token) lưu **write-only**: client chỉ thấy cờ `*_set`, không bao giờ đọc lại được giá trị thật.

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

## Deploy

Deploy lên GreenNode AgentBase bằng skill `agentbase-deploy` (build image `linux/amd64` → push Container Registry → tạo/cập nhật Agent Runtime, cấp secrets qua biến môi trường runtime). Chi tiết: [docs/deployment.md](docs/deployment.md).

Sau deploy: mở **endpoint public** ở tab ẩn danh → thấy web view (tạo bot/chat) là đạt.

## Bảo mật

- Mọi key nằm trong `.env` (đã gitignore) — **không bao giờ commit/push**. `.greennode.json` cũng gitignore.
- **Không** nhét secret vào Docker image (`Dockerfile`/`.dockerignore` đã loại `.env`).
- Secrets của bot (page token, app secret, telegram token) là **write-only** với client.
- Nếu key từng lộ trong lịch sử git → **xoay (rotate)** ngay.

---

Tài liệu thêm: [docs/setup.md](docs/setup.md) · [docs/architecture.md](docs/architecture.md) · [docs/eval.md](docs/eval.md) · [docs/deployment.md](docs/deployment.md) · [docs/spec.md](docs/spec.md)

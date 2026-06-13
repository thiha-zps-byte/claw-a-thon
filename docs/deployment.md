# Deploy lên GreenNode AgentBase

Theo đúng luồng 8 bước của Claw-a-thon. Agent của repo này là một `GreenNodeAgentBaseApp` chuẩn (`backend/app/main.py`) nên deploy được bằng **bộ skill AgentBase** chỉ bằng prompt.

## Chuẩn bị (Before You Start)

- **Docker Desktop** đang chạy (skill dùng để build & push image).
- **GitHub** repo PUBLIC để nộp bài.
- Thông tin từ email BTC: **Client ID + Client Secret**, **API Key (MaaS)**.
- Điền secrets vào `.env` (xem `.env.example`) — file này **gitignored**, không commit.
- `.greennode.json` từ `backend/.greennode.json.example` (cũng gitignored).

## Mô hình (MaaS)

Endpoint MaaS đã được xác minh phục vụ `google/gemma-4-31b-it` — đặt sẵn cho mọi tier trong `.env`. Nếu account bật thêm **Qwen** / **Minimax**, đổi `LLM_MODEL`/`FAST_MODEL`/`JUDGE_MODEL` tương ứng (vd `minimax/minimax-m2.5`).

## 8 bước (Live Demo flow)

1. **Login Portal** → đổi mật khẩu, lấy Client ID/Secret + API Key.
2. **Tạo GitHub repo** (PUBLIC), push source này lên.
3. **Build Agent** — đã có sẵn ở `backend/` (chạy local: `python -m app.main`).
4. **Import skill AgentBase** — clone `vngcloud/greennode-agentbase-skills` **cùng cấp** với repo (không lồng nhau).
5. **Chạy prompt deploy** — trong vibe code: *“Dùng skill này để deploy agent ở `backend/` lên AgentBase”*.
6. **Điền thông tin** — Client ID/Secret, API Key, chọn model (Gemma), runtime size **2×4** (đủ cho app này) hoặc 4×4.
7. **Docker build & push** — skill tự build từ `Dockerfile` (repo root, multi-stage: build frontend → chạy backend), đợi ~2–3 phút, kiểm tra **ACTIVE** trên portal.
8. **Push GitHub** — đảm bảo repo PUBLIC; copy endpoint public để submit.

## Kiểm tra sau deploy

- Portal → AgentBase: status **ACTIVE**.
- `GET /health` → Healthy.
- Mở endpoint public → thấy web view (UI tạo bot/chat).
- Gọi thử `POST /invocations` `{"bot_id":"<id>","message":"alo","uid":"voter"}`.

## Lưu ý

- **Không** nhét secret vào image — `Dockerfile`/`.dockerignore` đã loại `.env`, `.greennode.json`. Secrets cấp qua biến môi trường runtime trên AgentBase.
- `DATABASE_URL` mặc định là SQLite trong container (`/app/backend/data`). Dữ liệu sẽ reset khi container tái tạo — đủ cho demo; production nên gắn volume hoặc Postgres.

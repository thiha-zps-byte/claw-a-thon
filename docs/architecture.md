# Kiến trúc

**Modular monolith** (KHÔNG microservice): một ứng dụng deploy được, chia module theo domain với ranh giới rõ. Phase này một khối cho đơn giản & rẻ; ranh giới rõ để tách sau nếu cần.

## Layering (phụ thuộc một chiều)

```
api  →  services  →  (agents / skills / mcp / ingest)  →  db / config / core
```

Route mỏng (`app/api/`), logic ở service (`app/services/`), domain ở `agents/`, dữ liệu qua repository (`app/db/`). Không gọi ngược. Contract giữa tầng: JSON envelope (API) + dataclass/interface (nội bộ). Config tập trung `app/config.py` (mọi key đọc từ đây).

## Luồng một lượt chat

```
POST /api/chat (hoặc /invocations)
  → bot_service.chat(uid, bot_id, message)
      → load bot + documents (DB)  →  agent_service.run_turn
          → triage.classify(message)         # FAST model / rule-based
          → route:
              greeting/offtopic/abuse → canned fast reply (không gọi model chính)
              ontopic/complaint/high_stakes → ADK Agent (persona + docs + skills + MCP)
          → guards.polish + enforce_address    # de-bot + xưng hô
          → human delay hint
```

## Các module

| Module | Vai trò |
|---|---|
| `agents/base.py` | Agent gốc (ADK + LiteLlm → GreenNode MaaS) |
| `agents/persona.py` | System prompt: **xưng hô ghim**, anti-bot, grounding, an toàn, escalation |
| `agents/behavior/triage.py` | Phân loại tin → định tuyến + model tiering |
| `agents/behavior/guards.py` | De-bot, enforce xưng hô, canned replies, timing |
| `skills/` | Local tools (ADK FunctionTool): check_transaction, escalate… |
| `mcp/` | MCP toolsets (GreenNode Resource Gateway) — tắt mặc định |
| `ingest/` | Trích text: md/txt/csv/pdf/docx + ảnh (vision) |
| `services/context.py` | Token budgeting cho doc-stuffing (xưng hô/an toàn không bị cắt) |
| `services/agent_service.py` | Registry runner theo bot + orchestrate một lượt |
| `db/` | SQLModel models + repository (SQLite, WAL) |
| `core/errors.py` | Error envelope thống nhất |

## Scale (không cần microservice)

- App **stateless** + dữ liệu ở DB → chạy nhiều replica trên AgentBase.
- DB qua **repository pattern** → đổi SQLite → Postgres không đụng business logic.
- Lớp `ingest` tách sẵn → nâng **RAG** (vector store) khi tài liệu lớn.
- **Model tiering** + canned fast-path → giảm chi phí/độ trễ.
- Registry agent build từ DB (không hard in-memory) → nhiều instance dùng chung.

## Resilience

Không bao giờ 500 trần; mọi lỗi → envelope `{error, message(vi), detail, retryable}`. Context đầy → cắt theo thứ tự ưu tiên, **giữ nguyên xưng hô + an toàn**. LLM lỗi → câu xin lỗi + gợi ý thử lại. Chi tiết: mục §9 trong plan.

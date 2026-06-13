# Spec Kit — CS Agent Studio

## Use case
Đội vận hành game cần một **nhân viên CS ảo** trả lời người chơi 24/7 dựa trên tài liệu của game, đúng giọng và xưng hô riêng, an toàn và biết khi nào chuyển người thật.

## Track
Chat Agent.

## Actors
- **Người quản trị (owner)**: tạo bot, cấu hình xưng hô/persona, tải tài liệu, bật kỹ năng.
- **Người chơi (player)**: chat với bot để được hỗ trợ.
- **Hệ thống**: triage, sinh câu trả lời (ADK + MaaS), guard, lưu trữ.

## Kịch bản chính
1. Owner tạo bot “ZingSpeed” (gọi người chơi “tay đua”), tải FAQ.
2. Player hỏi “quên mật khẩu?” → bot trả lời theo tài liệu, đúng xưng hô.
3. Player phàn nàn/mất tiền → bot xoa dịu, xin thông tin, chuyển hỗ trợ.
4. Player hỏi linh tinh/đòi mật khẩu → bot từ chối an toàn.

## Input / Output (hợp đồng)

### Tạo bot — `POST /api/bots`
```json
// in
{ "name": "ZingSpeed Mobile", "description": "...", "player_term": "tay đua",
  "self_term": "mình", "tone": "...", "enabled_skills": ["escalate_to_human"] }
// out 201
{ "bot": { "id": "ab12...", "name": "...", "player_term": "tay đua", ... } }
```

### Nạp tài liệu — `POST /api/bots/{id}/documents` (multipart `files`)
```json
{ "documents": [ { "id": "...", "filename": "faq.md", "status": "ready", "char_count": 178 } ] }
```

### Chat — `POST /api/chat` (hoặc runtime `POST /invocations`)
```json
// in
{ "bot_id": "ab12...", "message": "mình quên mật khẩu" }   // header X-UID: <uid>
// out
{ "reply": "Tay đua đừng lo...", "category": "ontopic", "delay": 1.3, "bot_id": "ab12..." }
```

### Lỗi (mọi endpoint)
```json
{ "error": "validation_error", "message": "<vi>", "detail": "...", "retryable": false }
```

## Tools / Skills (mở rộng)
`check_transaction`, `lookup_account`, `get_event_info`, `escalate_to_human` (ADK FunctionTool) + MCP toolsets (GreenNode Resource Gateway, tắt mặc định).

## Phi chức năng
Không lộ secret/PII; không 500 trần; xưng hô không đổi; deploy được trên AgentBase; có bộ eval + Readiness Score.

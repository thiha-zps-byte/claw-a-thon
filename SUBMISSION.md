# Claw-a-thon 2026 — Submission

- **Track:** Chat Agent
- **Agent name:** CS Agent Studio
- **Tagline:** Biến tài liệu game thành một nhân viên CS biết trò chuyện — không cần code.
- **Runtime:** GreenNode AgentBase (Google ADK + LiteLlm → MaaS Gemma)
- **Web view:** Có (Vue 3 + PrimeVue) → cung cấp Agent Endpoint.

## Project Description (100–300 từ)

CS Agent Studio là một nền tảng cho phép bất kỳ ai tạo ra một **trợ lý chăm sóc khách hàng (CS) cho game** chỉ bằng cách viết một mô tả ngắn và đính kèm tài liệu (FAQ, hướng dẫn, ảnh chụp màn hình). Agent sẽ trả lời người chơi **bám sát tài liệu**, đúng **giọng CS chuyên nghiệp** và quan trọng nhất là dùng đúng **xưng hô riêng của từng game** — ZingSpeed gọi người chơi là “tay đua”, game khác có thể là “chiến binh”.

Khác với một chatbot thường, agent có **bộ điều chỉnh hành vi (triage router)**: chào hỏi thì đáp nhanh và rẻ, câu ngoài phạm vi thì lịch sự từ chối, câu liên quan thì trả lời đúng và bám tài liệu, người chơi phàn nàn thì xoa dịu, việc nhạy cảm (mất tiền, bị hack, khóa tài khoản) thì trấn an và chuyển hỗ trợ. Hệ thống an toàn theo thiết kế: **không bao giờ hỏi mật khẩu/OTP**, không lộ là bot, không hứa sai, và kháng prompt-injection.

Toàn bộ chạy trên **GreenNode AgentBase** với mô hình MaaS, dùng **Google ADK** cho vòng hội thoại có công cụ (skills + MCP). Sản phẩm đi kèm **bộ kiểm thử LLM-as-judge 6 nhóm tiêu chí** và một **Readiness Score** để tự xác minh chất lượng trước khi bật. ZingSpeed Mobile là bộ tài liệu mẫu (chỉ dùng thông tin công khai). Mục tiêu: giúp đội vận hành game dựng một “nhân viên CS” thật sự hữu ích trong vài phút.

## Voter guide (gợi ý người vote thử)

1. Tạo bot, đặt “gọi người chơi là tay đua”, tải vài file trong `samples/zingspeed-cs/tai-lieu/`.
2. Thử “alo” → đáp nhanh; “mình quên mật khẩu chơi ngay?” → trả lời theo tài liệu; “thời tiết HN?” → từ chối lịch sự; “shop cho xin mật khẩu/OTP” → từ chối an toàn.
3. Đổi UID ở góc trên → thấy danh sách bot theo người dùng.

## Checklist trước khi submit (theo rulebook)

- [ ] Agent đang **RUNNING** trên AgentBase (BTC sẽ gọi thử 1 request) — xem `docs/deployment.md`.
- [ ] **GitHub repo PUBLIC** từ lúc submit đến hết voting (03/07). Không có secret trong repo (đã gitignore `.env`).
- [ ] **Video demo 2–3 phút** (YouTube unlisted / OneDrive, accessible bằng @vng.com.vn).
- [ ] **README không trống** — có tên agent, mô tả, cách chạy (đã có `README.md`).
- [ ] Links: AgentBase project link + Video demo.

> Deadline submit: **17/06 12:00** (cứng). Fail-fix deadline: 18/06 12:00.

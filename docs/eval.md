# Bộ kiểm thử LLM-as-judge & Readiness Score

## Chạy
```bash
cd backend && . .venv/bin/activate
python -m tests.eval.runner --smoke      # tập con nhanh
python -m tests.eval.runner              # đầy đủ
python -m tests.eval.runner --json ../artifacts/eval.json
```

## Cách hoạt động
- `cases.yaml` — test case gom theo 6 nhóm tiêu chí. `hard: true` = gate cứng (an toàn + xưng hô).
- `judge.py` — chạy case qua agent thật → một model mạnh chấm ĐẠT/KHÔNG ĐẠT theo rubric.
- `runner.py` — tổng hợp pass-rate theo nhóm + hard-gate + p95 latency, in báo cáo, ghi JSON.

## 6 nhóm tiêu chí
- **A. Chất lượng hội thoại** — chào hỏi, xoa dịu phàn nàn, **xưng hô đúng (hard)**.
- **B. Chính xác** — grounding theo tài liệu, thừa nhận không biết.
- **C. An toàn (hard)** — không hỏi mật khẩu/OTP, kháng injection, không hứa sai.
- **D. Bền vững** — từ chối off-topic, hiểu teencode, hỏi lại khi mơ hồ.
- **E. Vận hành** — escalation đúng, thu đủ thông tin.
- **F. Cảm giác người thật** — không lộ bot, văn phong tự nhiên.

## Readiness Score
`bash scripts/test_all.sh [--smoke|--full]` chạy 4 tầng (boot · backend · frontend · LLM eval) → điểm 0–100 + gate cứng. Ghi `artifacts/readiness.json`.

> Lưu ý: judge dùng cùng model gemma (vì endpoint chỉ phục vụ gemma) nên kết quả LLM-judge có dao động nhỏ giữa các lần chạy; các tiêu chí an toàn quan trọng nhất được củng cố bằng kiểm tra rule-based trong `runner` (không hỏi mật khẩu/OTP, không lộ là bot).

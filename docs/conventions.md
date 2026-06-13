# Quy ước đặt tên & code

Ngôn ngữ: **code/comment tiếng Anh**, **UI + nội dung người chơi tiếng Việt**.

## Đặt tên

- Thư mục & file tài liệu/asset: `kebab-case` (`empty-state.svg`, `architecture.md`); file Python: `snake_case.py`.
- **Python**: hàm/biến `snake_case`, class `PascalCase`, hằng `UPPER_SNAKE`, private `_x`; docstring tiếng Anh.
- **Vue/TS**: component `PascalCase.vue`, composable `useXxx.ts`, biến/hàm `camelCase`, type/interface `PascalCase`, CSS `kebab-case`.
- **API**: path `kebab-case`, danh từ số nhiều (`/api/bots`, `/api/bots/{id}/documents`); JSON field `snake_case`.
- **DB**: bảng số nhiều `snake_case` (`bots`, `documents`), cột `snake_case`, FK `bot_id`.
- **Env**: `UPPER_SNAKE`.
- **Git**: branch `feat|fix|chore/...`; commit Conventional Commits.
- **Test**: `test_*.py` (pytest), `*.spec.ts` (Vitest), `*.e2e.ts` (Playwright), eval `cases.yaml`.

## Nguyên tắc

- Mỗi module một trách nhiệm; route mỏng, logic ở service.
- Secrets chỉ qua `app/config.py` (không `os.getenv` rải rác trừ config).
- Mọi lỗi tới client qua error envelope; không lộ stack/secret.
- Nút chỉ-icon **bắt buộc** có `aria-label` (a11y).
- Lint/format: `ruff` (backend), `eslint`/`vue-tsc` (frontend) phải xanh.

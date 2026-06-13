# Multi-stage build for GreenNode AgentBase.
# Stage 1 builds the Vue/PrimeVue frontend; stage 2 runs the Python agent and
# serves the built UI (the optional "web view" endpoint).
# Build context = repo root (cs-agent-studio/).

# --- Stage 1: frontend ---
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Stage 2: backend runtime ---
FROM python:3.13-slim
WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
# Built frontend served by the app (FRONTEND_DIST points here).
COPY --from=frontend /fe/dist /app/frontend/dist
ENV FRONTEND_DIST=/app/frontend/dist
# Bundled sample knowledge docs (one-click "Dùng tài liệu mẫu" in the UI).
COPY samples/ /app/samples
ENV SAMPLES_DIR=/app/samples/zingspeed-cs/tai-lieu
ENV HOST=0.0.0.0 PORT=8080
ENV DATABASE_URL=sqlite:////app/backend/data/cs_agent_studio.db

EXPOSE 8080
CMD ["python", "-m", "app.main"]

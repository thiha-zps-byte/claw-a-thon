"""Centralised configuration.

Every secret/setting is read here from the repo-local ``.env`` (gitignored) with a
fallback to real environment variables. No module should call ``os.getenv`` directly
for secrets — import ``settings`` from here instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# backend/app/config.py -> repo root is two parents up from `app`.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    """Load `<repo>/.env`; fall back to a legacy `backend/.env` if present."""
    candidates = [
        _REPO_ROOT / ".env",
        Path(os.getenv("ENV_FILE", "")) if os.getenv("ENV_FILE") else None,
    ]
    for path in candidates:
        if path and path.is_file():
            load_dotenv(path, override=False)


_load_env()


class ConfigError(RuntimeError):
    """Raised when required configuration is missing — fail fast at boot."""


def _require(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise ConfigError(
            f"Missing required env var '{key}'. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


@dataclass(frozen=True)
class Settings:
    # GreenNode
    greennode_client_id: str
    greennode_client_secret: str
    greennode_agent_identity: str
    # LLM endpoint
    llm_base_url: str
    llm_api_key: str
    # Model tiering
    llm_model: str
    fast_model: str
    vision_model: str
    idp_model: str
    judge_model: str
    # Storage
    database_url: str
    # Server
    port: int
    host: str
    cors_origins: tuple[str, ...]
    # Limits
    max_upload_mb: int
    context_token_budget: int
    # Optional gate for the "admin" UI mode (edits the shared bot). Empty = no gate.
    admin_token: str

    @property
    def upload_dir(self) -> Path:
        return _REPO_ROOT / "backend" / "uploads"

    @property
    def data_dir(self) -> Path:
        return _REPO_ROOT / "backend" / "data"

    def require_llm(self) -> None:
        """Validate that the LLM is configured (used by boot self-check)."""
        if not self.llm_base_url or not self.llm_api_key:
            raise ConfigError("LLM_BASE_URL and LLM_API_KEY are required.")


@lru_cache
def get_settings(require_secrets: bool = True) -> Settings:
    """Build the settings singleton. ``require_secrets`` off → for tests/CI."""
    getter = _require if require_secrets else _optional
    return Settings(
        greennode_client_id=_optional("GREENNODE_CLIENT_ID"),
        greennode_client_secret=_optional("GREENNODE_CLIENT_SECRET"),
        greennode_agent_identity=_optional("GREENNODE_AGENT_IDENTITY"),
        llm_base_url=getter("LLM_BASE_URL"),
        llm_api_key=getter("LLM_API_KEY"),
        # Default every tier to the model confirmed servable on the GreenNode
        # endpoint. Override per-tier in .env if your account has others enabled.
        llm_model=_optional("LLM_MODEL", "google/gemma-4-31b-it"),
        fast_model=_optional("FAST_MODEL", "google/gemma-4-31b-it"),
        vision_model=_optional("VISION_MODEL", "google/gemma-4-31b-it"),
        idp_model=_optional("IDP_MODEL", "greennode/idp"),
        judge_model=_optional("JUDGE_MODEL", "google/gemma-4-31b-it"),
        database_url=_optional("DATABASE_URL", "sqlite:///./data/cs_agent_studio.db"),
        port=int(_optional("PORT", "8080") or "8080"),
        host=_optional("HOST", "0.0.0.0"),
        cors_origins=tuple(
            o.strip()
            for o in _optional(
                "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if o.strip()
        ),
        max_upload_mb=int(_optional("MAX_UPLOAD_MB", "32") or "32"),
        context_token_budget=int(_optional("CONTEXT_TOKEN_BUDGET", "12000") or "12000"),
        admin_token=_optional("ADMIN_TOKEN"),
    )


# Convenience singleton. Tests can call get_settings.cache_clear() and rebuild.
try:
    settings = get_settings(require_secrets=False)
except ConfigError:  # pragma: no cover - defensive
    settings = None  # type: ignore[assignment]

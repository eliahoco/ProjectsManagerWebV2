"""
Application configuration settings
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Server
    PORT: int = 8401
    HOST: str = "127.0.0.1"  # Bind to localhost by default — set HOST=0.0.0.0 or ALLOW_LAN=true for LAN access
    ALLOW_LAN: bool = False  # Set to True (or HOST=0.0.0.0) to bind on all interfaces for LAN access
    DEBUG: bool = False  # Default to False for security; set DEBUG=true in .env for development
    ENVIRONMENT: str = "production"  # Default to production; set ENVIRONMENT=development in .env

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3601",
        "http://127.0.0.1:3601",
    ]
    FRONTEND_URL: str = "http://localhost:3601"

    # Database - use the shared Prisma database (relative path for portability)
    DATABASE_URL: str = "sqlite+aiosqlite:///../frontend/prisma/dev.db"

    # ChromaDB
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8402
    # CB-2729: per-call HTTP timeout (seconds) applied to the chromadb
    # HttpClient's underlying httpx session. chromadb 0.5.x constructs
    # `httpx.Client(timeout=None)` internally — heartbeat / list_collections
    # / count() block indefinitely on a stuck server (CLOSE_WAIT, slow-loris,
    # half-closed TCP). 2 s is a safe ceiling — every probe issued by
    # `get_status_payload()` returns well below that against a healthy
    # chromadb on loopback, while the worst-case stall is bounded by
    # `(N+2) * CHROMA_HTTP_TIMEOUT_S` instead of forever. Operators can
    # raise this via env if a remote/laggy chromadb deployment needs it.
    CHROMA_HTTP_TIMEOUT_S: float = 2.0

    # Claude API
    ANTHROPIC_API_KEY: str = ""

    # Frontend database path (for reading projects)
    FRONTEND_DB_PATH: str = "../frontend/prisma/dev.db"

    # Security settings
    WEBHOOK_SECRET: str = ""  # GitHub webhook secret - required in production
    REQUIRE_WEBHOOK_SIGNATURE: bool = True  # Set to False only for development

    # CB-2666: shared secret gating Origin-less reads of project-identifier
    # endpoints (currently /api/projects, /api/projects/{id}). Empty string
    # = pass-through (loopback-bind perimeter alone — preserves dev workflow).
    # When non-empty, callers without an allowed Origin must present
    # `X-Internal-Token: <value>` or get HTTP 401. See backend/app/security.py
    # and backend/docs/DOC_PIPELINE_RUNBOOK.md §3 for the deploy gate before
    # widening HOST/ALLOW_LAN.
    INTERNAL_API_TOKEN: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def effective_host(self) -> str:
        """Returns the actual host to bind to. Respects ALLOW_LAN override."""
        return "0.0.0.0" if self.ALLOW_LAN else self.HOST

    @property
    def is_development(self) -> bool:
        # Returns True only for the canonical development aliases
        # ({"development", "dev"}, case-insensitive). Anything else —
        # production / staging / unset / typos / padded values — returns
        # False. Fail-closed by design so callers can use this as a gate
        # for dev-only surfaces without having to re-encode the alias
        # contract at every call site.
        return self.ENVIRONMENT.lower() in {"development", "dev"}


settings = Settings()

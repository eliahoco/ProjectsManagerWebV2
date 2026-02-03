"""
Application configuration settings
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Server
    PORT: int = 8401
    HOST: str = "0.0.0.0"
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

    # Claude API
    ANTHROPIC_API_KEY: str = ""

    # Frontend database path (for reading projects)
    FRONTEND_DB_PATH: str = "../frontend/prisma/dev.db"

    # Security settings
    WEBHOOK_SECRET: str = ""  # GitHub webhook secret - required in production
    REQUIRE_WEBHOOK_SIGNATURE: bool = True  # Set to False only for development

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

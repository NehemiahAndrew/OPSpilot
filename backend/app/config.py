"""OpsPilot — application configuration.

Reads all settings from environment variables (or .env file) via
pydantic-settings. Every value has a sensible local-dev default so the
app boots without a fully-populated .env.
"""

from __future__ import annotations

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime config for the OpsPilot backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App -----------------------------------------------------------
    app_env: str = Field(default="development", alias="APP_ENV")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=True, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # --- API -----------------------------------------------------------
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    cors_origins: str = Field(
        default="http://localhost:3000", alias="CORS_ORIGINS"
    )
    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")

    # --- Database ------------------------------------------------------
    database_url: str = Field(
        default="postgresql://opspilot:opspilot@localhost:5432/opspilot",
        alias="DATABASE_URL",
    )
    database_pool_min: int = Field(default=1, alias="DATABASE_POOL_MIN")
    database_pool_max: int = Field(default=10, alias="DATABASE_POOL_MAX")

    # --- LLM -----------------------------------------------------------
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gpt-4o", alias="LLM_MODEL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # --- Orchestration -------------------------------------------------
    run_timeout_seconds: int = Field(default=300, alias="RUN_TIMEOUT_SECONDS")
    max_evidence_items: int = Field(default=50, alias="MAX_EVIDENCE_ITEMS")

    # --- Seed ----------------------------------------------------------
    seed_on_startup: bool = Field(default=False, alias="SEED_ON_STARTUP")

    @property
    def cors_origin_list(self) -> List[str]:
        """Parse CORS_ORIGINS into a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


# Singleton — imported everywhere
settings = Settings()


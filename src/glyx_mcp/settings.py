"""Application settings using Pydantic BaseSettings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API Keys
    openai_api_key: str
    anthropic_api_key: str | None = None
    openrouter_api_key: str | None = None
    claude_api_key: str | None = None

    # Langfuse Configuration
    langfuse_secret_key: str | None = None
    langfuse_public_key: str | None = None
    langfuse_host: str | None = None

    # Model Configuration
    default_orchestrator_model: str = "gpt-5"
    default_aider_model: str = "gpt-5"
    default_grok_model: str = "openrouter/x-ai/grok-4-fast"


# Global settings instance
settings = Settings()

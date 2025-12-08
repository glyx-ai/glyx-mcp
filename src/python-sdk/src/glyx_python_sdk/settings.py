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
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    openrouter_api_key: str | None = None
    claude_api_key: str | None = None
    mem0_api_key: str | None = None
    knock_api_key: str | None = None

    # Langfuse Configuration
    langfuse_secret_key: str | None = None
    langfuse_public_key: str | None = None
    langfuse_host: str | None = None

    # Supabase Configuration
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None

    # GitHub App Configuration
    github_app_id: str | None = None
    github_app_private_key: str | None = None
    github_app_client_id: str | None = None
    github_app_client_secret: str | None = None
    github_webhook_secret: str | None = None
    github_app_slug: str = "julian-e-acc"

    # Linear App Configuration
    linear_client_id: str | None = None
    linear_client_secret: str | None = None
    linear_webhook_secret: str | None = None
    linear_api_key: str | None = None

    # Model Configuration
    default_orchestrator_model: str = "gpt-5"
    default_aider_model: str = "gpt-5"
    default_grok_model: str = "openrouter/x-ai/grok-4-fast"

    # Docker Configuration
    container_name: str = "glyx-mcp"

    # Auth / JWT Configuration
    jwt_secret_key: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_expires_minutes: int = 15
    refresh_token_expires_days: int = 7
    auth_store_path: str = ".data/auth_store.json"


# Global settings instance
settings = Settings()

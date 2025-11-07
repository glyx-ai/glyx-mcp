"""Settings for glyx-mcp-tasks server."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class TaskServerSettings(BaseSettings):
    """Configuration for task tracking server."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Mem0 configuration
    mem0_api_key: str | None = None

    # Server configuration
    server_name: str = "glyx-mcp-tasks"
    log_level: str = "INFO"


settings = TaskServerSettings()

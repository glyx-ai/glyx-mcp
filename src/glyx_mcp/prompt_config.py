"""Prompt configuration system for glyx-mcp."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PromptConfig(BaseModel):
    """Configuration for enabled MCP prompts."""
    enabled_prompts: list[str] = Field(default_factory=lambda: ["agent"])


def get_config_path() -> Path:
    """Get the path to the prompt configuration file."""
    # Check for config in current directory first, then home directory
    local_config = Path.cwd() / ".glyx-mcp-prompts.json"
    if local_config.exists():
        return local_config
    return Path.home() / ".glyx-mcp-prompts.json"


def load_prompt_config() -> PromptConfig:
    """Load prompt configuration from .glyx-mcp-prompts.json

    Returns:
        PromptConfig with enabled_prompts list. Defaults to just 'agent' if no config found.
    """
    config_path = get_config_path()

    if config_path.exists():
        try:
            with open(config_path) as f:
                data = json.load(f)
                config = PromptConfig(**data)
                logger.info(f"Loaded prompt config from {config_path}")
                return config
        except Exception as e:
            logger.warning(f"Failed to load prompt config from {config_path}: {e}")

    # Default: only main agent prompt enabled
    logger.info("No prompt config found, using defaults (only 'agent' enabled)")
    return PromptConfig()


def register_prompts(mcp: Any, prompt_functions: dict[str, Callable[..., Any]]) -> None:
    """Register prompts that are enabled in config.

    Args:
        mcp: FastMCP server instance
        prompt_functions: Dict of prompt_name -> prompt_function

    Example:
        register_prompts(mcp, {
            "agent": agent_prompt,
            "aider": aider_prompt,
        })
    """
    config = load_prompt_config()

    for name, func in prompt_functions.items():
        if name in config.enabled_prompts:
            mcp.prompt()(func)
            logger.info(f"Registered prompt: {name}")
        else:
            logger.debug(f"Skipping disabled prompt: {name}")


def is_prompt_enabled(prompt_name: str) -> bool:
    """Check if a prompt is enabled in the configuration.

    Args:
        prompt_name: Name of the prompt to check

    Returns:
        True if the prompt is enabled, False otherwise
    """
    config = load_prompt_config()
    return prompt_name in config.enabled_prompts

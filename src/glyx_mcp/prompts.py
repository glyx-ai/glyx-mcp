"""MCP Prompt definitions for glyx-mcp agents."""

from __future__ import annotations

import logging
from pathlib import Path

from glyx_mcp.composable_agent import AgentKey, ComposableAgent

logger = logging.getLogger(__name__)


def list_available_agents() -> list[str]:
    """List all available agent configurations."""
    config_dir = Path(__file__).parent / "config"
    if not config_dir.exists():
        return []

    agents = []
    for config_file in config_dir.glob("*.json"):
        agent_name = config_file.stem
        agents.append(agent_name)

    return sorted(agents)


# Main composable prompt - always available
async def agent_prompt(
    agent_name: str,
    task: str,
    model: str | None = None,
    files: str | None = None,
    read_files: str | None = None,
    working_dir: str | None = None,
    max_turns: int | None = None,
) -> str:
    """
    Deploy any valid ComposableAgent as a subprocess to execute TaskConfig.
    """
    try:
        # Validate agent exists
        agent_key = AgentKey(agent_name)
    except ValueError:
        available = list_available_agents()
        return f"Unknown agent: {agent_name}. Available agents: {', '.join(available)}"

    # Build task config with only non-None parameters
    task_config = {"prompt": task}

    if model is not None:
        task_config["model"] = model
    if files is not None:
        task_config["files"] = files
    if read_files is not None:
        task_config["read_files"] = read_files
    if working_dir is not None:
        task_config["working_dir"] = working_dir
    if max_turns is not None:
        task_config["max_turns"] = max_turns

    try:
        result = await ComposableAgent.from_key(agent_key).execute(task_config, timeout=300)
        return result
    except Exception as e:
        logger.error(f"Error executing {agent_name}: {e}")
        return f"Error executing {agent_name}: {str(e)}"


# Aider-specific prompt
async def aider_prompt(task: str, files: str, model: str = "gpt-5", read_files: str | None = None) -> str:
    """
    Make fast, precise, and version-controlled changes using any OpenAI compatible model.
    """
    task_config = {
        "prompt": task,
        "files": files,
        "model": model,
    }

    if read_files:
        task_config["read_files"] = read_files

    try:
        result = await ComposableAgent.from_key(AgentKey.AIDER).execute(task_config, timeout=300)
        return result
    except Exception as e:
        logger.error(f"Error executing Aider: {e}")
        return f"Error executing Aider: {str(e)}"


# Grok-specific prompt
async def grok_prompt(question: str, model: str = "openrouter/x-ai/grok-4-fast") -> str:
    """
    Deploy instances of Grok 4 via Opencode CLI as part of a multi-agent workflow.
    """
    task_config = {
        "prompt": question,
        "model": model,
    }

    try:
        result = await ComposableAgent.from_key(AgentKey.GROK).execute(task_config, timeout=300)
        return result
    except Exception as e:
        logger.error(f"Error executing Grok: {e}")
        return f"Error executing Grok: {str(e)}"


# Claude-specific prompt
async def claude_prompt(
    task: str,
    model: str = "claude-sonnet-4-20250514",
    max_turns: int = 30,
    working_dir: str | None = None,
) -> str:
    """
    Deploy instances of Claude Code as part of a multi-agent workflow.
    """
    task_config = {
        "prompt": task,
        "model": model,
        "max_turns": max_turns,
    }

    if working_dir:
        task_config["working_dir"] = working_dir

    try:
        result = await ComposableAgent.from_key(AgentKey.CLAUDE).execute(task_config, timeout=600)
        return result
    except Exception as e:
        logger.error(f"Error executing Claude: {e}")
        return f"Error executing Claude: {str(e)}"

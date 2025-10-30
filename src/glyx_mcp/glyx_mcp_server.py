"""FastMCP server for coding agents with Aider integration."""

from __future__ import annotations

import logging

from fastmcp import FastMCP

from glyx_mcp.composable_agent import AgentKey, ComposableAgent

logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("glyxcob")


@mcp.tool
async def use_aider(
    prompt: str,
    files: str,
    model: str = "gpt-5",
    read_files: str | None = None,
) -> str:
    """Use Aider AI coding assistant for file-based code editing tasks.

    Args:
        prompt: The coding task or instruction for Aider
        files: Comma-separated list of files to edit (required)
        model: LLM model to use (default: gpt-5)
        read_files: Comma-separated list of read-only reference files (optional)

    Returns:
        Aider's response with code changes and explanations
    """
    task_config = {
        "prompt": prompt,
        "files": files,
        "model": model,
    }

    if read_files:
        task_config["read_files"] = read_files

    return await ComposableAgent.from_key(AgentKey.AIDER).execute(task_config, timeout=300)


@mcp.tool
async def use_grok(
    prompt: str,
    model: str = "openrouter/x-ai/grok-4-fast",
) -> str:
    """Use Grok 4 AI model via OpenCode CLI for general reasoning tasks.

    Args:
        prompt: The task or question for Grok
        model: LLM model to use (default: openrouter/x-ai/grok-4-fast)

    Returns:
        Grok's response to the prompt
    """
    task_config = {
        "prompt": prompt,
        "model": model,
    }

    return await ComposableAgent.from_key(AgentKey.GROK).execute(task_config, timeout=300)


if __name__ == "__main__":
    # Run server with stdio transport (default for MCP)
    mcp.run()

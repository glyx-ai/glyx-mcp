"""Aider tool for AI-powered code editing."""

from __future__ import annotations

from glyx_mcp.composable_agent import AgentKey, ComposableAgent


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

    result = await ComposableAgent.from_key(AgentKey.AIDER).execute(task_config, timeout=300)
    return result.output

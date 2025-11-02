"""Aider tool for AI-powered code editing."""

from __future__ import annotations

from fastmcp import Context

from glyx_mcp.composable_agent import AgentKey, ComposableAgent


async def use_aider(
    prompt: str,
    files: str,
    ctx: Context,
    model: str = "gpt-5",
    read_files: str | None = None,
) -> str:
    """Use Aider AI coding assistant for file-based code editing tasks.

    Args:
        prompt: The coding task or instruction for Aider
        files: Comma-separated list of files to edit (required)
        model: LLM model to use (default: gpt-5)
        read_files: Comma-separated list of read-only reference files (optional)
        ctx: FastMCP context for logging (injected by FastMCP)

    Returns:
        Aider's response with code changes and explanations
    """
    await ctx.info("Starting Aider execution", extra={"model": model, "files": files})

    task_config = {
        "prompt": prompt,
        "files": files,
        "model": model,
    }

    if read_files:
        task_config["read_files"] = read_files
        await ctx.debug("Including read-only files", extra={"read_files": read_files})

    result = await ComposableAgent.from_key(AgentKey.AIDER).execute(task_config, timeout=300)

    await ctx.info(
        "Aider execution completed",
        extra={"exit_code": result.exit_code, "execution_time": result.execution_time},
    )

    return result.output

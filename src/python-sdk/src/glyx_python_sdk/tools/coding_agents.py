"""Coding agent tools for AI-powered code editing and reasoning."""

from __future__ import annotations

from fastmcp import Context

from glyx_python_sdk import AgentKey, ComposableAgent


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


async def use_grok(
    prompt: str,
    ctx: Context,
    model: str = "openrouter/x-ai/grok-code-fast-1",
) -> str:
    """Use Grok 4 AI model via OpenCode CLI for general reasoning tasks.

    Args:
        prompt: The task or question for Grok
        model: LLM model to use (default: openrouter/x-ai/grok-4-fast)
        ctx: FastMCP context for logging (injected by FastMCP)

    Returns:
        Grok's response to the prompt
    """
    await ctx.info("Starting Grok execution", extra={"model": model})

    task_config = {
        "prompt": prompt,
        "model": model,
    }

    result = await ComposableAgent.from_key(AgentKey.GROK).execute(task_config, timeout=300)

    await ctx.info(
        "Grok execution completed",
        extra={"exit_code": result.exit_code, "execution_time": result.execution_time},
    )

    return result.output


async def use_opencode(
    prompt: str,
    ctx: Context,
    model: str | None = None,
    subcmd: str = "run",
) -> str:
    """Use OpenCode CLI for general AI coding and reasoning tasks.

    Args:
        prompt: The prompt or question for OpenCode
        model: Model to use in 'provider/model-id' format (e.g., 'opencode/grok-code')
        subcmd: OpenCode subcommand (default: 'run')
        ctx: FastMCP context for logging (injected by FastMCP)

    Returns:
        OpenCode's response to the prompt
    """
    await ctx.info("Starting OpenCode execution", extra={"model": model, "subcmd": subcmd})

    task_config: dict[str, str] = {
        "prompt": prompt,
        "subcmd": subcmd,
    }

    result = await ComposableAgent.from_key(AgentKey.OPENCODE).execute(task_config, timeout=300)

    await ctx.info(
        "OpenCode execution completed",
        extra={"exit_code": result.exit_code, "execution_time": result.execution_time},
    )

    return result.output

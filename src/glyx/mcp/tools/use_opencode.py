"""OpenCode tool for general AI coding and reasoning tasks."""

from __future__ import annotations

from fastmcp import Context

from glyx.core.agent import AgentKey, ComposableAgent


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

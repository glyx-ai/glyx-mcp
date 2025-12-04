"""Grok tool for AI-powered reasoning."""

from __future__ import annotations

from fastmcp import Context

from glyx_python_sdk import AgentKey, ComposableAgent


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

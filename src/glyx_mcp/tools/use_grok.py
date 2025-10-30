"""Grok tool for AI-powered reasoning."""

from __future__ import annotations

from glyx_mcp.composable_agent import AgentKey, ComposableAgent


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

    result = await ComposableAgent.from_key(AgentKey.GROK).execute(task_config, timeout=300)
    return result.output

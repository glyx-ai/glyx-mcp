"""OpenCode tool for general AI coding and reasoning tasks."""

from __future__ import annotations

from glyx_mcp.composable_agent import AgentKey, ComposableAgent


async def use_opencode(
    prompt: str,
    model: str | None = None,
    subcmd: str = "run",
) -> str:
    """Use OpenCode CLI for general AI coding and reasoning tasks.

    Args:
        prompt: The prompt or question for OpenCode
        model: Model to use in 'provider/model-id' format (e.g., 'opencode/grok-code')
        subcmd: OpenCode subcommand (default: 'run')

    Returns:
        OpenCode's response to the prompt
    """
    task_config: dict[str, str] = {
        "prompt": prompt,
        "subcmd": subcmd,
    }

    if model:
        task_config["model"] = model

    result = await ComposableAgent.from_key(AgentKey.OPENCODE).execute(task_config, timeout=300)
    return result.output

"""Agent registry with auto-discovery from JSON configs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from glyx.core.agent import ComposableAgent

if TYPE_CHECKING:
    from fastmcp import Context, FastMCP

logger = logging.getLogger(__name__)


def discover_and_register_agents(
    mcp: FastMCP,
    agents_dir: str | Path,
    timeout: int = 300,
) -> dict[str, ComposableAgent]:
    """Auto-discover agent configs and register as MCP tools.

    Args:
        mcp: FastMCP server instance
        agents_dir: Directory containing agent JSON configs
        timeout: Default timeout for agent execution (seconds)

    Returns:
        Dictionary mapping agent names to ComposableAgent instances
    """
    agents_path = Path(agents_dir)
    logger.info(f"Discovering agents in {agents_path}")

    agents: dict[str, ComposableAgent] = {}

    for json_file in agents_path.glob("*.json"):
        try:
            agent = ComposableAgent.from_file(json_file)
            agent_name = agent.config.agent_key
            agents[agent_name] = agent

            # Create dynamic wrapper function with closure
            def make_agent_wrapper(
                agent_instance: ComposableAgent, timeout_val: int
            ):
                async def agent_wrapper(
                    prompt: str,
                    ctx: Context,
                    model: str = "gpt-5",
                    files: str | None = None,
                    read_files: str | None = None,
                    **kwargs: str,
                ) -> str:
                    """Dynamically generated agent tool."""
                    await ctx.info(f"Starting {agent_instance.config.agent_key} execution")

                    task_config = {
                        "prompt": prompt,
                        "model": model,
                        **kwargs,
                    }

                    if files:
                        task_config["files"] = files
                    if read_files:
                        task_config["read_files"] = read_files

                    result = await agent_instance.execute(task_config, timeout=timeout_val)

                    await ctx.info(
                        f"{agent_instance.config.agent_key} execution completed",
                        extra={"exit_code": result.exit_code, "execution_time": result.execution_time},
                    )

                    return result.output

                return agent_wrapper

            agent_wrapper = make_agent_wrapper(agent, timeout)

            # Set function metadata
            agent_wrapper.__name__ = f"use_{agent_name}"
            agent_wrapper.__doc__ = agent.config.description or f"Execute {agent_name} agent"

            # Register with FastMCP
            mcp.tool(agent_wrapper)
            logger.info(f"Registered agent: {agent_name}")

        except Exception as e:
            logger.error(f"Failed to load agent from {json_file}: {e}")
            continue

    logger.info(f"Registered {len(agents)} agents")
    return agents

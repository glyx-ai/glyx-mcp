"""Agent registry with auto-discovery from JSON configs and Supabase."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from agents import SQLiteSession
from fastmcp import Context

from glyx_sdk.agent import ComposableAgent
from glyx_sdk.supabase_loader import load_agents_from_supabase

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Session database location - use /tmp for cloud environments
SESSION_DB = Path(os.environ.get("GLYX_SESSION_DB", "/tmp/glyx_sessions.db"))


def make_agent_wrapper(agent_instance: ComposableAgent, timeout_val: int):
    """Create a wrapper function for an agent to be registered as an MCP tool."""

    async def agent_wrapper(
        prompt: str,
        ctx: Context,
        model: str = "gpt-5",
        files: str | None = None,
        read_files: str | None = None,
        conversation_id: str | None = None,
    ) -> str:
        """Dynamically generated agent tool."""
        session_id = conversation_id or str(uuid.uuid4())
        session = SQLiteSession(session_id, str(SESSION_DB))

        contextualized_prompt = prompt
        try:
            history = await session.get_items(limit=10)
            if history:
                context_str = "\n".join(
                    [f"{item.get('role', 'unknown')}: {item.get('content', '')}" for item in history[-5:]]
                )
                contextualized_prompt = f"Previous conversation:\n{context_str}\n\nCurrent request: {prompt}"
                await ctx.info(f"Loaded {len(history[-5:])} messages from session history")
        except Exception as e:
            logger.warning(f"Failed to load session history: {e}")

        try:
            user_message_content = prompt
            if files:
                user_message_content += f"\nFiles: {files}"
            if read_files:
                user_message_content += f"\nRead files: {read_files}"

            await session.add_items([{"role": "user", "content": user_message_content}])
            logger.info(f"Saved user message to session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to save user message to session: {e}")

        await ctx.info(f"Starting {agent_instance.config.agent_key} with {model}")

        task_config = {"prompt": contextualized_prompt, "model": model}
        if files:
            task_config["files"] = files
            await ctx.info(f"Processing files: {files}")
        if read_files:
            task_config["read_files"] = read_files
            await ctx.info(f"Reading files: {read_files}")

        await ctx.info(f"Executing {agent_instance.config.agent_key} subprocess...")
        result = await agent_instance.execute(task_config, timeout=timeout_val, ctx=ctx)

        if result.success:
            await ctx.info(
                f"{agent_instance.config.agent_key} completed successfully",
                extra={"execution_time": f"{result.execution_time:.2f}s"},
            )
        else:
            await ctx.info(
                f"{agent_instance.config.agent_key} failed",
                extra={"exit_code": result.exit_code, "execution_time": f"{result.execution_time:.2f}s"},
            )

        try:
            await session.add_items([{"role": "assistant", "content": result.output}])
            logger.info(f"Saved assistant response to session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to save assistant response to session: {e}")

        return result.output

    return agent_wrapper


def discover_and_register_agents(
    mcp: FastMCP,
    agents_dir: str | Path,
    timeout: int = 300,
    load_from_supabase: bool = True,
    user_id: str | None = None,
) -> dict[str, ComposableAgent]:
    """Auto-discover agent configs and register as MCP tools.

    Args:
        mcp: FastMCP server instance
        agents_dir: Directory containing agent JSON configs
        timeout: Default timeout for agent execution (seconds)
        load_from_supabase: Whether to also load agents from Supabase
        user_id: Optional user ID for loading user-specific agents

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

            agent_wrapper = make_agent_wrapper(agent, timeout)
            agent_wrapper.__name__ = f"use_{agent_name}"
            agent_wrapper.__doc__ = agent.config.description or f"Execute {agent_name} agent"

            mcp.tool(agent_wrapper)
            logger.info(f"Registered agent: {agent_name}")

        except Exception as e:
            logger.error(f"Failed to load agent from {json_file}: {e}")
            continue

    if load_from_supabase:
        db_configs = load_agents_from_supabase(user_id)
        for config in db_configs:
            if config.agent_key in agents:
                logger.info(f"Supabase agent '{config.agent_key}' overrides file-based agent")

            agent = ComposableAgent(config)
            agents[config.agent_key] = agent

            agent_wrapper = make_agent_wrapper(agent, timeout)
            agent_wrapper.__name__ = f"use_{config.agent_key}"
            agent_wrapper.__doc__ = config.description or f"Execute {config.agent_key} agent"
            mcp.tool(agent_wrapper)
            logger.info(f"Registered Supabase agent: {config.agent_key}")

    logger.info(f"Registered {len(agents)} agents total")
    return agents


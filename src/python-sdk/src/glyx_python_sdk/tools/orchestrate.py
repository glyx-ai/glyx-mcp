"""Orchestrator MCP tool."""

from __future__ import annotations

import logging

from fastmcp import Context
from glyx_python_sdk import GlyxOrchestrator

logger = logging.getLogger(__name__)


async def orchestrate(task: str, ctx: Context) -> str:
    """
    Orchestrate complex tasks by coordinating multiple AI agents with deep reasoning and stuff.

    Args:
        task: The task description to orchestrate across multiple agents
    """
    from agents.items import ItemHelpers, MessageOutputItem

    logger.info(f"orchestrate tool received - task: {task!r}")

    orchestrator = GlyxOrchestrator(
        agent_name="MCPOrchestrator",
        model="openrouter/anthropic/claude-sonnet-4",
        mcp_servers=[],
        session_id="mcp-orchestrate",
    )

    try:
        output_parts = []
        async for item in orchestrator.run_prompt_streamed_items(task):
            if isinstance(item, MessageOutputItem):
                text = ItemHelpers.text_message_output(item)
                output_parts.append(text)

        await orchestrator.cleanup()
        return f"✅ Orchestration completed successfully\n\n{''.join(output_parts)}"
    except Exception as e:
        logger.error(f"Orchestration failed: {e}")
        return f"❌ Orchestration failed: {e}"

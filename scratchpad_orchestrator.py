#!/usr/bin/env python3
"""Scratchpad for testing orchestrator with real FastMCP context."""

from __future__ import annotations

import asyncio
import logging
import sys

from fastmcp import FastMCP
from fastmcp.server.context import Context
from fastmcp.utilities.logging import get_logger

from glyx_mcp.orchestration.orchestrator import Orchestrator
from glyx_mcp.settings import settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)

logger = logging.getLogger(__name__)

# Configure FastMCP client logging
to_client_logger = get_logger(name="fastmcp.server.context.to_client")
to_client_logger.setLevel(level=logging.DEBUG)


async def main() -> None:
    """Run orchestrator using FastMCP's context infrastructure."""
    logger.info("=" * 80)
    logger.info("ORCHESTRATOR TEST - WITH REAL FASTMCP CONTEXT")
    logger.info("=" * 80)

    logger.info("Initializing orchestrator without context (standalone mode)...")
    orchestrator = Orchestrator(ctx=None)

    # Task that uses multiple agents
    task = "Explain what prime numbers are and write a Python function to check if a number is prime"

    logger.info(f"Task: {task}")
    logger.info("=" * 80)
    logger.info("STARTING ORCHESTRATION")
    logger.info("=" * 80)

    # Run orchestration
    result = await orchestrator.orchestrate(task)

    # Display results
    logger.info("=" * 80)
    logger.info("ORCHESTRATION COMPLETE")
    logger.info("=" * 80)

    logger.info(f"Success: {result.success}")

    if result.plan:
        logger.info(f"Plan Reasoning: {result.plan.reasoning}")
        logger.info(f"Tasks Executed ({len(result.plan.tasks)}):")
        for i, task_item in enumerate(result.plan.tasks, 1):
            logger.info(f"  {i}. {task_item.agent}: {task_item.task_description}")

    logger.info(f"Agent Results ({len(result.agent_results)}):")
    for i, agent_result in enumerate(result.agent_results, 1):
        success_icon = "✓" if agent_result["success"] else "✗"
        logger.info(f"  {success_icon} Agent {i}: {agent_result.get('agent', 'unknown')}")
        if not agent_result["success"]:
            logger.warning(f"    Error: {agent_result.get('error', 'Unknown error')}")

    logger.info(f"Final Synthesis: {result.synthesis}")

    if result.error:
        logger.error(f"Error: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())

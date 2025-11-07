"""FastMCP server for coding agents with Aider integration."""

from __future__ import annotations

import logging
import sys

from fastmcp import FastMCP, Context
from fastmcp.utilities.logging import get_logger
from langfuse import Langfuse

from pathlib import Path

from glyx.core.registry import discover_and_register_agents
from glyx.mcp.orchestration.orchestrator import Orchestrator
from glyx.mcp.settings import settings
from glyx.mcp.tools.interact_with_user import ask_user
from glyx.mcp.tools.use_memory import (
    save_memory,
    search_memory,
)
from glyx.tasks.server import mcp as tasks_mcp
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
    ],
    force=True,
)

logger = logging.getLogger(__name__)


# Optional Langfuse instrumentation (only if keys are configured)
langfuse = None
if settings.langfuse_public_key and settings.langfuse_secret_key:
    langfuse = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    if not langfuse.auth_check():
        logger.warning(
            "Langfuse authentication failed. Tracing will be disabled. "
            "Check LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_HOST in your .env file."
        )
        langfuse = None
    else:
        logger.info("Langfuse instrumented. Preparing OpenAI agent instrumentation...")
        OpenAIAgentsInstrumentor().instrument()
else:
    logger.info("Langfuse not configured. Tracing disabled.")



# Configure FastMCP client logging (messages sent to MCP clients)
to_client_logger = get_logger(name="fastmcp.server.context.to_client")
to_client_logger.setLevel(level=logging.DEBUG)


mcp = FastMCP("glyx-mcp")

# Register tools with MCP server
logger.info("Initializing MCP tools...")

# Auto-discover and register agents from JSON configs
agents_dir = Path(__file__).parent.parent.parent.parent / "agents"
discover_and_register_agents(mcp, agents_dir)

# Register non-agent tools manually
mcp.tool(ask_user)
mcp.tool(search_memory)
mcp.tool(save_memory)

# Mount task tracking server
logger.info("Mounting task tracking server...")
mcp.mount(tasks_mcp)



# Register orchestrator as a tool (not prompt) due to Claude Code bug with MCP prompts
# See: https://github.com/anthropics/claude-code/issues/6657
@mcp.tool
async def orchestrate(
    task: str,
    ctx: Context,
) -> str:
    """
    Orchestrate complex tasks by coordinating multiple AI agents with deep reasoning and stuff.

    Args:
        task: The task description to orchestrate across multiple agents
    """
    logger.info(f"orchestrate tool received - task: {task!r}")
    orchestrator = Orchestrator(ctx=ctx, model="gpt-5")

    # Run orchestration synchronously and return the result
    # (The orchestrator internally runs agents in parallel via OpenAI Agents SDK)
    try:
        result = await orchestrator.orchestrate(task)
        return f"✅ Orchestration completed successfully\n\n{result.output}"
    except Exception as e:
        logger.error(f"Orchestration failed: {e}")
        return f"❌ Orchestration failed: {e}"


def main() -> None:
    """Run the FastMCP server."""
    mcp.run()


if __name__ == "__main__":
    main()

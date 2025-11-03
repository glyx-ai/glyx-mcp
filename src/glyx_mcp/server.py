"""FastMCP server for coding agents with Aider integration."""

from __future__ import annotations

import logging
import sys

from fastmcp import FastMCP, Context
from fastmcp.utilities.logging import get_logger
from langfuse import Langfuse

from glyx_mcp.orchestration.orchestrator import Orchestrator
from glyx_mcp.settings import settings
from glyx_mcp.tools.interact_with_user import ask_user
from glyx_mcp.tools.use_aider import use_aider
from glyx_mcp.tools.use_grok import use_grok
from glyx_mcp.tools.use_memory import (
    save_memory,
    search_memory,
)
from glyx_mcp.tools.use_opencode import use_opencode
from glyx_mcp.tools.use_shot_scraper import use_shot_scraper
from glyx_mcp_tasks.server import mcp as tasks_mcp
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


langfuse = Langfuse(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    host=settings.langfuse_host,
)
if not langfuse.auth_check():
    raise RuntimeError(
        "Langfuse authentication failed. Please check LANGFUSE_PUBLIC_KEY, "
        "LANGFUSE_SECRET_KEY, and LANGFUSE_HOST in your .env file."
    )
logger.info("Langfuse instrumented. Preparing OpenAI agent instrumentation...")
OpenAIAgentsInstrumentor().instrument()



# Configure FastMCP client logging (messages sent to MCP clients)
to_client_logger = get_logger(name="fastmcp.server.context.to_client")
to_client_logger.setLevel(level=logging.DEBUG)


mcp = FastMCP("glyx-mcp")

# Register tools with MCP server
logger.info("Initializing MCP tools...")
mcp.tool(ask_user)
mcp.tool(use_aider)
mcp.tool(use_grok)
mcp.tool(use_opencode)
mcp.tool(use_shot_scraper)
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

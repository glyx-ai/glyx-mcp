"""FastMCP server for coding agents with Aider integration."""

from __future__ import annotations

import atexit
import logging
import os
import sys

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger
from langfuse import get_client, observe

from glyx_mcp import prompts
from glyx_mcp.tools.use_aider import use_aider
from glyx_mcp.tools.use_grok import use_grok
from glyx_mcp.tools.use_opencode import use_opencode

# Configure logging to output to both file and stderr with DEBUG level

langfuse = get_client()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
    ],
    force=True,
)

logger = logging.getLogger(__name__)

# Configure FastMCP client logging (messages sent to MCP clients)
to_client_logger = get_logger(name="fastmcp.server.context.to_client")
to_client_logger.setLevel(level=logging.DEBUG)


mcp = FastMCP("glyx-mcp")

# Register tools with MCP server
mcp.tool(use_aider)
mcp.tool(use_grok)
mcp.tool(use_opencode)

# Register prompts - hardcoded for simplicity
mcp.prompt()(prompts.agent_prompt)
mcp.prompt()(prompts.orchestrate_prompt)
logger.info("Registered prompts: agent_prompt, orchestrate_prompt")

@observe
def main() -> None:
    """Run the FastMCP server."""
    mcp.run()


if __name__ == "__main__":
    main()

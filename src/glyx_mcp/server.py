"""MCP server setup and tool registration."""

from __future__ import annotations

import logging

from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger

from glyx_python_sdk import discover_and_register_agents, search_memory, save_memory
from glyx_python_sdk.tools.interact_with_user import ask_user
from glyx_python_sdk.tools.session_tools import get_session_messages, list_sessions
from glyx_python_sdk.tools.orchestrate import orchestrate


logger = logging.getLogger(__name__)

# Create FastMCP instance
mcp = FastMCP("glyx-ai")

# Configure FastMCP client logging
to_client_logger = get_logger(name="fastmcp.server.context.to_client")
to_client_logger.setLevel(level=logging.INFO)

# Register tools with MCP server
logger.info("Initializing MCP tools...")

# Register agents from SDK configs
discover_and_register_agents(mcp)

# Register non-agent tools manually
mcp.tool(ask_user)
mcp.tool(search_memory)
mcp.tool(save_memory)
mcp.tool(list_sessions)
mcp.tool(get_session_messages)

# Register orchestrator as a tool (not prompt) due to Claude Code bug with MCP prompts
# See: https://github.com/anthropics/claude-code/issues/6657
mcp.tool(orchestrate)


def main() -> None:
    """Run the FastMCP server (stdio mode for Claude Code)."""
    mcp.run()

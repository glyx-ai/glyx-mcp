"""MCP server setup and tool registration."""

from __future__ import annotations

import logging

from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger

from glyx_python_sdk import discover_and_register_agents, search_memory, save_memory
from glyx_python_sdk.tools.interact_with_user import ask_user
from glyx_python_sdk.tools.session_tools import get_session_messages, list_sessions
from glyx_python_sdk.tools.orchestrate import orchestrate
from glyx_python_sdk.tools.device_dispatch import (
    dispatch_task,
    run_on_device,
    start_agent,
    stop_agent,
    list_devices,
    get_device_status,
    get_task_status,
)


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

# Register device dispatch tools (for iOS app MCP client)
mcp.tool(dispatch_task)
mcp.tool(run_on_device)
mcp.tool(start_agent)
mcp.tool(stop_agent)
mcp.tool(list_devices)
mcp.tool(get_device_status)
mcp.tool(get_task_status)


def main() -> None:
    """Run the FastMCP server (stdio mode for Claude Code)."""
    mcp.run()

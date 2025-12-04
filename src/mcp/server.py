"""MCP server setup and tool registration."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger

from glyx_python_sdk import discover_and_register_agents, search_memory, save_memory
import glyx_python_sdk

from glyx_python_sdk.tools.agent_crud import create_agent, delete_agent, get_agent, list_agents
from glyx_python_sdk.tools.interact_with_user import ask_user
from glyx_python_sdk.tools.session_tools import get_session_messages, list_sessions
from glyx_python_sdk.tools.orchestrate import orchestrate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
    force=True,
)

logger = logging.getLogger(__name__)

# Create FastMCP instance
mcp = FastMCP("glyx-ai")

# Configure FastMCP client logging
to_client_logger = get_logger(name="fastmcp.server.context.to_client")
to_client_logger.setLevel(level=logging.INFO)

# Register tools with MCP server
logger.info("Initializing MCP tools...")

# Auto-discover and register agents from JSON configs
# Agents are in the SDK package (go up from src/glyx_python_sdk/__init__.py to src/ then to agents/)
_sdk_src_path = Path(glyx_python_sdk.__file__).parent.parent  # src/python-sdk/src
_sdk_root = _sdk_src_path.parent  # src/python-sdk
agents_dir = _sdk_root / "agents"
discover_and_register_agents(mcp, agents_dir)

# Register non-agent tools manually
mcp.tool(ask_user)
mcp.tool(search_memory)
mcp.tool(save_memory)
mcp.tool(list_sessions)
mcp.tool(get_session_messages)

# Agent CRUD tools (Supabase-backed)
mcp.tool(create_agent)
mcp.tool(list_agents)
mcp.tool(delete_agent)
mcp.tool(get_agent)

# Register orchestrator as a tool (not prompt) due to Claude Code bug with MCP prompts
# See: https://github.com/anthropics/claude-code/issues/6657
mcp.tool(orchestrate)


def main() -> None:
    """Run the FastMCP server (stdio mode for Claude Code)."""
    mcp.run()

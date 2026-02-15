"""MCP server setup and tool registration."""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import get_access_token
from fastmcp.utilities.logging import get_logger

from glyx_python_sdk import discover_and_register_agents, search_memory, save_memory
from glyx_python_sdk.tools.interact_with_user import ask_user
from glyx_python_sdk.tools.session_tools import get_session_messages, list_sessions
from glyx_python_sdk.tools.orchestrate import orchestrate
from glyx_python_sdk.tools.device_dispatch import (
    dispatch_task as _dispatch_task,
    run_on_device as _run_on_device,
    start_agent as _start_agent,
    stop_agent as _stop_agent,
    list_devices as _list_devices,
    get_device_status as _get_device_status,
    get_task_status as _get_task_status,
)

logger = logging.getLogger(__name__)


def _get_user_id() -> Optional[str]:
    """Get user_id from JWT claims via FastMCP auth."""
    token = get_access_token()
    if token and token.claims:
        return token.claims.get("sub")
    return None


# Supabase JWT verification
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vpopliwokdmpxhmippwc.supabase.co")
auth = JWTVerifier(
    jwks_uri=f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json",
    issuer=f"{SUPABASE_URL}/auth/v1",
    audience="authenticated",
)

# Create FastMCP instance with auth
mcp = FastMCP("glyx-ai", auth=auth)

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

# ============================================================================
# Device dispatch tools with auth - extract user_id from JWT claims
# ============================================================================


@mcp.tool()
async def dispatch_task(device_id: str, agent_type: str, prompt: str, cwd: Optional[str] = None) -> dict:
    """Dispatch a task to a local agent on a paired device."""
    return await _dispatch_task(device_id, agent_type, prompt, cwd, user_id=_get_user_id())


@mcp.tool()
async def run_on_device(device_id: str, command: str, cwd: Optional[str] = None) -> dict:
    """Run a shell command on a paired device."""
    return await _run_on_device(device_id, command, cwd, user_id=_get_user_id())


@mcp.tool()
async def start_agent(device_id: str, agent_type: str, cwd: Optional[str] = None) -> dict:
    """Start an AI agent on a paired device."""
    return await _start_agent(device_id, agent_type, cwd, user_id=_get_user_id())


@mcp.tool()
async def stop_agent(device_id: str, agent_type: str) -> dict:
    """Stop a running agent on a paired device."""
    return await _stop_agent(device_id, agent_type, user_id=_get_user_id())


@mcp.tool()
async def list_devices() -> dict:
    """List all paired devices for the current user."""
    return await _list_devices(user_id=_get_user_id())


@mcp.tool()
async def get_device_status(device_id: str) -> dict:
    """Get detailed status of a specific device."""
    return await _get_device_status(device_id, user_id=_get_user_id())


@mcp.tool()
async def get_task_status(task_id: str) -> dict:
    """Get status of a dispatched task."""
    return await _get_task_status(task_id, user_id=_get_user_id())


def main() -> None:
    """Run the FastMCP server (stdio mode for Claude Code)."""
    mcp.run()

"""MCP server setup and tool registration."""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastmcp import FastMCP
from fastmcp.server.auth import TokenVerifier, AccessToken
from fastmcp.utilities.logging import get_logger
from supabase import create_client

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
from fastmcp.server.dependencies import get_access_token

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vpopliwokdmpxhmippwc.supabase.co")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


def _get_user_id() -> Optional[str]:
    """Get user_id from validated access token."""
    token = get_access_token()
    if token and token.claims:
        return token.claims.get("sub")
    return None


class SupabaseTokenVerifier(TokenVerifier):
    """Token verifier that validates via Supabase auth.get_user()."""

    async def verify_token(self, token: str) -> AccessToken | None:
        """Validate token by calling Supabase auth API."""
        try:
            logger.info(f"[AUTH] Verifying token, ANON_KEY set: {bool(SUPABASE_ANON_KEY)}")
            client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
            response = client.auth.get_user(token)
            logger.info(f"[AUTH] get_user response: {response.user is not None}")
            if response.user:
                user_id = str(response.user.id)
                return AccessToken(
                    token=token,
                    client_id="glyx-ios",
                    scopes=[],
                    claims={
                        "sub": user_id,
                        "email": response.user.email,
                    },
                )
            return None
        except Exception as e:
            logger.warning(f"Token validation failed: {e}")
            return None


# Create auth provider
auth = SupabaseTokenVerifier()

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
# Device dispatch tools with auth - extract user_id from access token
# ============================================================================


@mcp.tool()
async def dispatch_task(device_id: str, agent_type: str, prompt: str, cwd: Optional[str] = None) -> dict:
    """Dispatch a task to a local agent on a paired device."""
    logger.info(f"[DISPATCH] dispatch_task called - cwd={cwd}")
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


@mcp.tool()
async def list_directory(path: str = "~") -> list[dict]:
    """List contents of a directory. Returns list of {name, isDirectory, size}."""
    import os
    import stat

    expanded = os.path.expanduser(path)
    return [
        {
            "name": entry.name,
            "isDirectory": entry.is_dir(),
            "size": entry.stat().st_size if entry.is_file() else 0,
        }
        for entry in os.scandir(expanded)
        if entry.name not in (".", "..")
    ]


def main() -> None:
    """Run the FastMCP server (stdio mode for Claude Code)."""
    mcp.run()

"""Glyx Cloud MCP — per-user agent server.

Single-file FastMCP server with owner-only auth via Supabase.
Each user gets their own Cloud Run instance with OWNER_USER_ID set.
"""

import os
import subprocess

from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from supabase import create_client

OWNER = os.environ["OWNER_USER_ID"]
SUPA_URL = os.environ.get("SUPABASE_URL", "https://vpopliwokdmpxhmippwc.supabase.co")
SUPA_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "sb_publishable_PFYg1B15pdweWFaL6BRDCQ_SnX-BbZf",
)


class OwnerOnly(TokenVerifier):
    """Only the owner (matched by OWNER_USER_ID env var) can access this server."""

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            user = create_client(SUPA_URL, SUPA_KEY).auth.get_user(token)
            if user.user and str(user.user.id) == OWNER:
                return AccessToken(
                    token=token,
                    client_id="glyx-ios",
                    scopes=[],
                    claims={"sub": str(user.user.id)},
                )
        except Exception:
            pass
        return None


mcp = FastMCP("glyx-cloud", auth=OwnerOnly())


@mcp.tool()
async def run_command(command: str, cwd: str = "/workspace") -> str:
    """Run a shell command."""
    r = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=120)
    return r.stdout + r.stderr


@mcp.tool()
async def read_file(path: str) -> str:
    """Read a file."""
    with open(path) as f:
        return f.read()


@mcp.tool()
async def write_file(path: str, content: str) -> str:
    """Write a file."""
    with open(path, "w") as f:
        f.write(content)
    return f"Wrote {len(content)} bytes to {path}"


@mcp.tool()
async def list_files(path: str = "/workspace") -> list[dict]:
    """List directory contents."""
    return [
        {"name": e.name, "is_dir": e.is_dir(), "size": e.stat().st_size if e.is_file() else 0}
        for e in os.scandir(path)
    ]

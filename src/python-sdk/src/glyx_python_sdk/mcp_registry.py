"""MCP Server Configuration using environment variables."""

import logging
import os

from agents.mcp import MCPServerStdio, MCPServerStdioParams

logger = logging.getLogger(__name__)

# Get API keys from environment
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENMEMORY_API_KEY = os.environ.get("OPENMEMORY_API_KEY", "")

# Context7 - Documentation retrieval
context7_params: MCPServerStdioParams = {
    "command": "npx",
    "args": ["-y", "@upstash/context7-mcp"],
}
zen_mcp_params: MCPServerStdioParams = {
    "command": "sh",
    "args": [
        "-c",
        "exec $(which uvx || echo uvx) --from git+https://github.com/BeehiveInnovations/zen-mcp-server.git zen-mcp-server",
    ],
    "env": {
        "PATH": f"{os.path.expanduser('~/.local/bin')}:/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin",
        "GEMINI_API_KEY": GEMINI_API_KEY,
    },
}
serena_params: MCPServerStdioParams = {
    "command": "sh",
    "args": [
        "-c",
        "exec $(which uvx || echo uvx) --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project /home/parallels/glyx",
    ],
    "env": {
        "PATH": f"{os.path.expanduser('~/.local/bin')}:/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin",
    },
}

CONTEXT7 = MCPServerStdio(
    params=context7_params,
    name="Context7",
    client_session_timeout_seconds=10,
)
SERENA = MCPServerStdio(
    params=serena_params,
    cache_tools_list=True,
    name="Serena",
    client_session_timeout_seconds=10,
)

ZEN = MCPServerStdio(
    params=zen_mcp_params,
    cache_tools_list=True,
    name="Zen",
    client_session_timeout_seconds=10,
)
openmemory_params: MCPServerStdioParams = {
    "command": "npx",
    "args": [
        "-y",
        "openmemory",
        OPENMEMORY_API_KEY,
    ],
    "env": {
        "OPENMEMORY_API_KEY": OPENMEMORY_API_KEY,
        "CLIENT_NAME": "openmemory",
    },
}

OPENMEMORY = MCPServerStdio(
    params=openmemory_params,
    name="OpenMemory",
    client_session_timeout_seconds=10,
)

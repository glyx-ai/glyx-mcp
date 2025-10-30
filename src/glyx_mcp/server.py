"""FastMCP server for coding agents with Aider integration."""

from __future__ import annotations

import logging

from fastmcp import FastMCP

from glyx_mcp import prompts
from glyx_mcp.prompt_config import register_prompts
from glyx_mcp.tools.use_aider import use_aider
from glyx_mcp.tools.use_grok import use_grok

logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("glyx-mcp")

# Register tools with MCP server
mcp.tool(use_aider)
mcp.tool(use_grok)

# Register prompts dynamically based on config
register_prompts(mcp, {
    "agent": prompts.agent_prompt,
    "aider": prompts.aider_prompt,
    "grok": prompts.grok_prompt,
    "claude": prompts.claude_prompt,
})


def main() -> None:
    """Run the FastMCP server."""
    mcp.run()


if __name__ == "__main__":
    main()

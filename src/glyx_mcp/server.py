"""FastMCP server for coding agents with Aider integration."""

from __future__ import annotations

import atexit
import logging
import os
import sys

from dotenv import load_dotenv
from fastmcp import FastMCP
from langfuse import get_client

# Load environment variables from .env file
load_dotenv()

from glyx_mcp import prompts
from glyx_mcp.tools.use_aider import use_aider
from glyx_mcp.tools.use_grok import use_grok
from glyx_mcp.tools.use_opencode import use_opencode

# Configure logging to stderr only with INFO level
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
    ],
    force=True,
)

logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("glyx-mcp")

# Register tools with MCP server
mcp.tool(use_aider)
mcp.tool(use_grok)
mcp.tool(use_opencode)

# Register prompts - hardcoded for simplicity
mcp.prompt()(prompts.agent_prompt)
mcp.prompt()(prompts.orchestrate_prompt)
logger.info("Registered prompts: agent_prompt, orchestrate_prompt")

# Initialize Langfuse tracing
public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
secret_key = os.getenv("LANGFUSE_SECRET_KEY")
if public_key and secret_key:
    langfuse = get_client()
    logger.info(f"✅ Langfuse tracing enabled")
    logger.info(f"   Host: {os.getenv('LANGFUSE_HOST', 'https://cloud.langfuse.com')}")
    logger.info(f"   Public Key: {public_key[:20]}...")

    def flush_langfuse() -> None:
        logger.info("📤 Flushing traces to Langfuse...")
        langfuse.flush()
        logger.info("✅ Traces flushed successfully")

    atexit.register(flush_langfuse)
else:
    logger.info("⚠️  Langfuse tracing disabled (LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY not set)")


def main() -> None:
    """Run the FastMCP server."""
    mcp.run()


if __name__ == "__main__":
    main()

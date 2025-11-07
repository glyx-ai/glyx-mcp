"""FastMCP server for task tracking and orchestration."""

from __future__ import annotations

import logging
import sys

from fastmcp import FastMCP

from glyx.tasks.tools.task_tools import assign_task, create_task, update_task

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
    ],
    force=True,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("glyx-mcp-tasks")

# Register task tracking tools
logger.info("Initializing task tracking tools...")
mcp.tool(create_task)
mcp.tool(assign_task)
mcp.tool(update_task)


def main() -> None:
    """Run the FastMCP task tracking server."""
    logger.info("Starting glyx-mcp-tasks server...")
    mcp.run()


if __name__ == "__main__":
    main()

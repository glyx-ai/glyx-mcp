"""Main entry point for glyx-mcp server."""

from glyx_mcp.glyx_mcp_server import mcp


def main() -> None:
    """Run the FastMCP server."""
    # Run server with stdio transport (default for MCP)
    mcp.run()


if __name__ == "__main__":
    main()

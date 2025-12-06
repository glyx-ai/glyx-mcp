"""Integration tests using FastMCP Client to invoke glyx-mcp tools.

These tests verify that:
1. The MCP server can be instantiated and connected via Client
2. Tools are properly registered and discoverable
3. Tools can be invoked with parameters
4. Results are returned correctly
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from glyx_mcp.server import mcp


@pytest.mark.integration
class TestFastMCPClient:
    """Test glyx-mcp server using FastMCP Client."""

    @pytest.mark.asyncio
    async def test_client_connection(self) -> None:
        """Test that client can connect to the MCP server."""
        client = Client(mcp)

        async with client:
            # Verify connectivity with ping
            response = await client.ping()
            assert response is not None

    @pytest.mark.asyncio
    async def test_list_tools(self) -> None:
        """Test that all expected tools are registered."""
        client = Client(mcp)

        async with client:
            tools = await client.list_tools()

            # Extract tool names
            tool_names = [tool.name for tool in tools]

            # Verify expected tools are present
            assert "use_aider" in tool_names
            assert "use_grok" in tool_names
            assert "use_opencode" in tool_names

            # Verify we have the expected number of tools
            assert len(tool_names) >= 3

    @pytest.mark.asyncio
    async def test_tool_has_parameters(self) -> None:
        """Test that tools have proper parameter definitions."""
        client = Client(mcp)

        async with client:
            tools = await client.list_tools()

            # Find the use_aider tool
            aider_tool = next((t for t in tools if t.name == "use_aider"), None)
            assert aider_tool is not None

            # Verify it has an input schema
            assert aider_tool.inputSchema is not None

            # Verify required parameters exist
            properties = aider_tool.inputSchema.get("properties", {})
            assert "prompt" in properties
            assert "files" in properties
            assert "model" in properties

    @pytest.mark.asyncio
    async def test_call_tool_invocation(self) -> None:
        """Test calling a tool through the client."""
        client = Client(mcp)

        async with client:
            # Call the tool - it will execute the subprocess
            # We expect it to return a result (success or failure)
            result = await client.call_tool(
                "use_grok",
                {"prompt": "What is 2+2?", "model": "openrouter/x-ai/grok-4-fast"},
            )

            # Verify we got a result back
            assert result is not None
            assert hasattr(result, "content")

            # The result should have content (even if it's an error message)
            assert len(result.content) > 0


@pytest.mark.integration
class TestToolInvocationWithMock:
    """Test tool invocation patterns with mocked subprocess."""

    @pytest.mark.asyncio
    async def test_agent_tool_has_standard_parameters(self) -> None:
        """Test that agent tools have the standard parameter schema."""
        client = Client(mcp)

        async with client:
            tools = await client.list_tools()

            # Check a few agent tools have the standard schema
            for tool_name in ["use_aider", "use_grok", "use_opencode"]:
                tool = next((t for t in tools if t.name == tool_name), None)
                assert tool is not None, f"Tool {tool_name} not found"

                schema = tool.inputSchema
                assert schema["type"] == "object"

                properties = schema["properties"]
                assert "prompt" in properties
                assert "model" in properties

                # Verify required fields
                required = schema.get("required", [])
                assert "prompt" in required

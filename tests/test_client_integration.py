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
class TestPrompts:
    """Test MCP prompts registration."""

    @pytest.mark.asyncio
    async def test_list_prompts(self) -> None:
        """Test that prompts are properly registered."""
        client = Client(mcp)

        async with client:
            prompts = await client.list_prompts()

            # Extract prompt names
            prompt_names = [p.name for p in prompts]

            # Verify expected prompts are present
            assert "agent_prompt" in prompt_names
            assert "orchestrate_prompt" in prompt_names

            # Verify we have at least 2 prompts
            assert len(prompt_names) >= 2

    @pytest.mark.asyncio
    async def test_prompt_has_arguments(self) -> None:
        """Test that prompts have proper argument definitions."""
        client = Client(mcp)

        async with client:
            prompts = await client.list_prompts()

            # Find the agent_prompt
            agent_prompt = next((p for p in prompts if p.name == "agent_prompt"), None)
            assert agent_prompt is not None

            # Verify it has arguments
            assert agent_prompt.arguments is not None
            assert len(agent_prompt.arguments) > 0

            # Verify key arguments exist
            arg_names = [arg.name for arg in agent_prompt.arguments]
            assert "agent_name" in arg_names
            assert "task" in arg_names


@pytest.mark.integration
class TestToolInvocationWithMock:
    """Test tool invocation patterns with mocked subprocess."""

    @pytest.mark.asyncio
    async def test_aider_tool_parameters(self) -> None:
        """Test that use_aider tool accepts correct parameters."""
        client = Client(mcp)

        async with client:
            # Get tool definition
            tools = await client.list_tools()
            aider_tool = next((t for t in tools if t.name == "use_aider"), None)
            assert aider_tool is not None

            # Verify input schema structure
            schema = aider_tool.inputSchema
            assert schema["type"] == "object"

            properties = schema["properties"]
            assert properties["prompt"]["type"] == "string"
            assert properties["files"]["type"] == "string"
            assert properties["model"]["type"] == "string"

            # Verify required fields
            required = schema.get("required", [])
            assert "prompt" in required
            assert "files" in required

    @pytest.mark.asyncio
    async def test_grok_tool_parameters(self) -> None:
        """Test that use_grok tool accepts correct parameters."""
        client = Client(mcp)

        async with client:
            # Get tool definition
            tools = await client.list_tools()
            grok_tool = next((t for t in tools if t.name == "use_grok"), None)
            assert grok_tool is not None

            # Verify input schema structure
            schema = grok_tool.inputSchema
            properties = schema["properties"]

            assert properties["prompt"]["type"] == "string"
            assert properties["model"]["type"] == "string"

            # Verify required fields
            required = schema.get("required", [])
            assert "prompt" in required

    @pytest.mark.asyncio
    async def test_opencode_tool_parameters(self) -> None:
        """Test that use_opencode tool accepts correct parameters."""
        client = Client(mcp)

        async with client:
            # Get tool definition
            tools = await client.list_tools()
            opencode_tool = next((t for t in tools if t.name == "use_opencode"), None)
            assert opencode_tool is not None

            # Verify input schema structure
            schema = opencode_tool.inputSchema
            properties = schema["properties"]

            assert properties["prompt"]["type"] == "string"
            assert "model" in properties
            assert "subcmd" in properties

            # Verify required fields
            required = schema.get("required", [])
            assert "prompt" in required

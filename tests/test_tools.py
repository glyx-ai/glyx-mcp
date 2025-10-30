"""Unit tests for glyx-mcp MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from glyx_mcp.composable_agent import AgentKey, AgentResult
from glyx_mcp.tools.use_aider import use_aider
from glyx_mcp.tools.use_grok import use_grok


class TestUseAider:
    """Tests for the use_aider MCP tool."""

    @pytest.mark.asyncio
    async def test_use_aider_basic(self) -> None:
        """Test use_aider with basic parameters."""
        # Arrange
        mock_result = AgentResult(
            stdout="Aider response: Code updated successfully",
            stderr="",
            exit_code=0,
            timed_out=False,
            execution_time=2.5,
            command=["aider", "--message", "test"]
        )
        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock(return_value=mock_result)

        with patch("glyx_mcp.tools.use_aider.ComposableAgent.from_key", return_value=mock_agent) as mock_from_key:
            # Act
            result = await use_aider(
                prompt="Add a docstring to the main function",
                files="src/main.py",
                model="gpt-5"
            )

            # Assert
            mock_from_key.assert_called_once_with(AgentKey.AIDER)
            mock_agent.execute.assert_called_once_with(
                {
                    "prompt": "Add a docstring to the main function",
                    "files": "src/main.py",
                    "model": "gpt-5"
                },
                timeout=300
            )
            assert result == "Aider response: Code updated successfully"


class TestUseGrok:
    """Tests for the use_grok MCP tool."""

    @pytest.mark.asyncio
    async def test_use_grok_basic(self) -> None:
        """Test use_grok with basic parameters."""
        # Arrange
        mock_result = AgentResult(
            stdout="Grok response: The answer is 42",
            stderr="",
            exit_code=0,
            timed_out=False,
            execution_time=1.2,
            command=["opencode", "run"]
        )
        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock(return_value=mock_result)

        with patch("glyx_mcp.tools.use_grok.ComposableAgent.from_key", return_value=mock_agent) as mock_from_key:
            # Act
            result = await use_grok(
                prompt="What is the meaning of life?",
                model="openrouter/x-ai/grok-4-fast"
            )

            # Assert
            mock_from_key.assert_called_once_with(AgentKey.GROK)
            mock_agent.execute.assert_called_once_with(
                {
                    "prompt": "What is the meaning of life?",
                    "model": "openrouter/x-ai/grok-4-fast"
                },
                timeout=300
            )
            assert result == "Grok response: The answer is 42"

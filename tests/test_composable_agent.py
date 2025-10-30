"""Unit tests for ComposableAgent command building and execution."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from glyx_mcp.composable_agent import (
    AgentConfig,
    AgentResult,
    ArgSpec,
    ComposableAgent,
)


class TestCommandBuilding:
    """Tests for command building logic in ComposableAgent."""

    @pytest.mark.asyncio
    async def test_command_building_with_mixed_argument_types(self) -> None:
        """Test command construction with flags, bools, and positional args."""

        # Create a test config (mimics aider.json structure)
        config = AgentConfig(
            agent_key="test_agent",
            command="test_cli",
            args={
                "prompt": ArgSpec(flag="--message", type="string", required=True),
                "model": ArgSpec(flag="--model", type="string", default="gpt-4"),
                "files": ArgSpec(flag="--file", type="string", required=True),
                "no_git": ArgSpec(flag="--no-git", type="bool", default=True),
                "yes_always": ArgSpec(flag="--yes-always", type="bool", default=True),
            }
        )

        agent = ComposableAgent(config)

        # Mock the subprocess execution to capture the command
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"success", b""))
        mock_process.returncode = 0

        with patch('asyncio.create_subprocess_exec', return_value=mock_process) as mock_exec:
            task_config = {
                "prompt": "Add docstring",
                "files": "main.py",
                "model": "gpt-4o"  # Override default
            }

            result = await agent.execute(task_config, timeout=30)

            # Verify the command structure
            call_args = mock_exec.call_args[0]
            assert call_args == (
                "test_cli",
                "--message", "Add docstring",
                "--model", "gpt-4o",
                "--file", "main.py",
                "--no-git",
                "--yes-always"
            )

            # Verify result structure
            assert result.success is True
            assert result.exit_code == 0
            assert isinstance(result, AgentResult)

    @pytest.mark.asyncio
    async def test_command_building_without_optional_args(self) -> None:
        """Test that optional args with None values are omitted."""
        config = AgentConfig(
            agent_key="test",
            command="test_cli",
            args={
                "prompt": ArgSpec(flag="-p", type="string", required=True),
                "optional": ArgSpec(flag="--opt", type="string", default=None),
            }
        )

        agent = ComposableAgent(config)
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch('asyncio.create_subprocess_exec', return_value=mock_process) as mock_exec:
            result = await agent.execute({"prompt": "test"}, timeout=10)

            call_args = mock_exec.call_args[0]
            assert call_args == ("test_cli", "-p", "test")
            assert "--opt" not in call_args
            assert result.success is True

    @pytest.mark.asyncio
    async def test_command_building_with_positional_args(self) -> None:
        """Test that args with empty flags are added as positional."""
        config = AgentConfig(
            agent_key="test",
            command="test_cli",
            args={
                "subcmd": ArgSpec(flag="", type="string", default="run"),
                "message": ArgSpec(flag="-m", type="string", required=True),
            }
        )

        agent = ComposableAgent(config)
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch('asyncio.create_subprocess_exec', return_value=mock_process) as mock_exec:
            result = await agent.execute({"message": "hello"}, timeout=10)

            call_args = mock_exec.call_args[0]
            assert call_args[0] == "test_cli"
            assert "run" in call_args  # Positional arg included
            assert "-m" in call_args
            assert "hello" in call_args
            assert result.success is True

    @pytest.mark.asyncio
    async def test_command_building_with_default_values(self) -> None:
        """Test that default values are used when not provided in task_config."""
        config = AgentConfig(
            agent_key="test",
            command="test_cli",
            args={
                "model": ArgSpec(flag="--model", type="string", default="default-model"),
                "timeout": ArgSpec(flag="--timeout", type="string", default="30"),
            }
        )

        agent = ComposableAgent(config)
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch('asyncio.create_subprocess_exec', return_value=mock_process) as mock_exec:
            # Don't provide any config - should use defaults
            result = await agent.execute({}, timeout=10)

            call_args = mock_exec.call_args[0]
            assert "--model" in call_args
            assert "default-model" in call_args
            assert "--timeout" in call_args
            assert "30" in call_args
            assert result.success is True

    @pytest.mark.asyncio
    async def test_command_building_bool_false_omitted(self) -> None:
        """Test that boolean flags with False value are omitted."""
        config = AgentConfig(
            agent_key="test",
            command="test_cli",
            args={
                "verbose": ArgSpec(flag="--verbose", type="bool", default=False),
                "quiet": ArgSpec(flag="--quiet", type="bool", default=False),
            }
        )

        agent = ComposableAgent(config)
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch('asyncio.create_subprocess_exec', return_value=mock_process) as mock_exec:
            result = await agent.execute({}, timeout=10)

            call_args = mock_exec.call_args[0]
            assert call_args == ("test_cli",)  # No boolean flags added
            assert "--verbose" not in call_args
            assert "--quiet" not in call_args
            assert result.success is True

    @pytest.mark.asyncio
    async def test_command_building_bool_true_included(self) -> None:
        """Test that boolean flags with True value are included without value."""
        config = AgentConfig(
            agent_key="test",
            command="test_cli",
            args={
                "verbose": ArgSpec(flag="--verbose", type="bool", default=False),
            }
        )

        agent = ComposableAgent(config)
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch('asyncio.create_subprocess_exec', return_value=mock_process) as mock_exec:
            result = await agent.execute({"verbose": True}, timeout=10)

            call_args = mock_exec.call_args[0]
            assert "--verbose" in call_args
            # Make sure it's just the flag, no value after it
            verbose_idx = call_args.index("--verbose")
            assert verbose_idx == len(call_args) - 1  # It's the last item
            assert result.success is True


class TestAgentResult:
    """Tests for AgentResult dataclass."""

    def test_agent_result_success_property(self) -> None:
        """Test that success property correctly evaluates exit code and timeout."""
        # Success case
        result = AgentResult(
            stdout="output",
            stderr="",
            exit_code=0,
            timed_out=False,
            execution_time=1.0
        )
        assert result.success is True

        # Failure - non-zero exit code
        result = AgentResult(
            stdout="",
            stderr="error",
            exit_code=1,
            timed_out=False,
            execution_time=1.0
        )
        assert result.success is False

        # Failure - timed out
        result = AgentResult(
            stdout="",
            stderr="",
            exit_code=0,
            timed_out=True,
            execution_time=30.0
        )
        assert result.success is False

    def test_agent_result_output_property(self) -> None:
        """Test that output property combines stdout and stderr correctly."""
        # Only stdout
        result = AgentResult(
            stdout="hello world",
            stderr="",
            exit_code=0,
            timed_out=False,
            execution_time=1.0
        )
        assert result.output == "hello world"

        # Both stdout and stderr
        result = AgentResult(
            stdout="hello",
            stderr="warning",
            exit_code=0,
            timed_out=False,
            execution_time=1.0
        )
        assert result.output == "hello\nSTDERR: warning"

        # Only stderr
        result = AgentResult(
            stdout="",
            stderr="error occurred",
            exit_code=1,
            timed_out=False,
            execution_time=1.0
        )
        assert result.output == "\nSTDERR: error occurred"

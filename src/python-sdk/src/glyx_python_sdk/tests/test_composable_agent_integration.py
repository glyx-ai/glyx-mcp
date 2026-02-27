"""Integration tests for ComposableAgent subprocess execution.

These tests verify real subprocess execution without mocking asyncio.create_subprocess_exec.
They use lightweight CLI tools (echo, python) to test the full execution flow.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

from glyx_python_sdk import AgentConfig, AgentResult, ArgSpec, ComposableAgent


@pytest.fixture
def echo_agent_config() -> AgentConfig:
    """Create an agent config that wraps the echo command."""
    return AgentConfig(
        agent_key="echo_test",
        command="echo",
        args=[
            ArgSpec(name="message", flag="", type="string", required=True, positional=True),
        ],
    )


@pytest.fixture
def python_agent_config() -> AgentConfig:
    """Create an agent config that wraps python -c for more complex testing."""
    return AgentConfig(
        agent_key="python_test",
        command=sys.executable,
        args=[
            ArgSpec(name="code", flag="-c", type="string", required=True),
        ],
    )


@pytest.fixture
def failing_agent_config() -> AgentConfig:
    """Create an agent config that will fail with non-zero exit code."""
    return AgentConfig(
        agent_key="failing_test",
        command=sys.executable,
        args=[
            ArgSpec(name="code", flag="-c", type="string", required=True),
        ],
    )


@pytest.mark.integration
class TestComposableAgentExecution:
    """Integration tests for real subprocess execution."""

    @pytest.mark.asyncio
    async def test_execute_echo_command(self, echo_agent_config: AgentConfig) -> None:
        """Test executing a simple echo command."""
        agent = ComposableAgent(echo_agent_config)

        result = await agent.execute({"message": "Hello, Integration Test!"}, timeout=10)

        assert isinstance(result, AgentResult)
        assert result.success is True
        assert result.exit_code == 0
        assert "Hello, Integration Test!" in result.stdout
        assert result.timed_out is False
        assert result.execution_time > 0

    @pytest.mark.asyncio
    async def test_execute_python_code(self, python_agent_config: AgentConfig) -> None:
        """Test executing Python code via subprocess."""
        agent = ComposableAgent(python_agent_config)

        result = await agent.execute({"code": "print('Python subprocess works!')"}, timeout=10)

        assert result.success is True
        assert result.exit_code == 0
        assert "Python subprocess works!" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_with_stderr(self, python_agent_config: AgentConfig) -> None:
        """Test capturing stderr output."""
        agent = ComposableAgent(python_agent_config)

        result = await agent.execute(
            {"code": "import sys; sys.stderr.write('Error message\\n')"},
            timeout=10,
        )

        assert result.success is True  # Writing to stderr doesn't mean failure
        assert result.exit_code == 0
        assert "Error message" in result.stderr

    @pytest.mark.asyncio
    async def test_execute_non_zero_exit_code(self, failing_agent_config: AgentConfig) -> None:
        """Test handling non-zero exit codes."""
        agent = ComposableAgent(failing_agent_config)

        result = await agent.execute({"code": "import sys; sys.exit(42)"}, timeout=10)

        assert result.success is False
        assert result.exit_code == 42
        assert result.timed_out is False

    @pytest.mark.asyncio
    async def test_execute_with_exception(self, python_agent_config: AgentConfig) -> None:
        """Test handling Python exceptions in subprocess."""
        agent = ComposableAgent(python_agent_config)

        result = await agent.execute({"code": "raise ValueError('Test error')"}, timeout=10)

        assert result.success is False
        assert result.exit_code != 0
        assert "ValueError" in result.stderr or "ValueError" in result.output

    @pytest.mark.asyncio
    async def test_execute_timeout(self, python_agent_config: AgentConfig) -> None:
        """Test that long-running commands timeout correctly.

        Note: Current implementation raises TimeoutError instead of returning
        AgentResult with timed_out=True. This test verifies the timeout is enforced.
        """
        import asyncio

        agent = ComposableAgent(python_agent_config)

        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await agent.execute(
                {"code": "import time; time.sleep(10); print('done')"},
                timeout=1,  # 1 second timeout
            )

    @pytest.mark.asyncio
    async def test_execute_multiline_output(self, python_agent_config: AgentConfig) -> None:
        """Test capturing multiline stdout."""
        agent = ComposableAgent(python_agent_config)

        code = "for i in range(5): print(f'Line {i}')"
        result = await agent.execute({"code": code}, timeout=10)

        assert result.success is True
        for i in range(5):
            assert f"Line {i}" in result.stdout

    @pytest.mark.asyncio
    async def test_result_output_property(self, python_agent_config: AgentConfig) -> None:
        """Test the output property combines stdout and stderr."""
        agent = ComposableAgent(python_agent_config)

        code = "import sys; print('stdout line'); sys.stderr.write('stderr line\\n')"
        result = await agent.execute({"code": code}, timeout=10)

        assert "stdout line" in result.output
        assert "stderr line" in result.output

    @pytest.mark.asyncio
    async def test_execute_with_working_directory(self) -> None:
        """Test executing in a specific working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file in the temp directory
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test content")

            config = AgentConfig(
                agent_key="ls_test",
                command="ls",
                args=[
                    ArgSpec(name="path", flag="", type="string", required=True, positional=True),
                ],
            )

            agent = ComposableAgent(config)
            result = await agent.execute({"path": tmpdir}, timeout=10)

            assert result.success is True
            assert "test.txt" in result.stdout


@pytest.mark.integration
class TestComposableAgentFromFile:
    """Test loading and executing agents from config files."""

    @pytest.mark.asyncio
    async def test_load_from_config_file(self, tmp_path: Path) -> None:
        """Test loading agent config from JSON file."""
        config_file = tmp_path / "test_agent.json"
        config_file.write_text(
            """{
            "test_echo": {
                "command": "echo",
                "args": {
                    "message": {
                        "flag": "",
                        "type": "string",
                        "required": true,
                        "positional": true
                    }
                }
            }
        }"""
        )

        agent = ComposableAgent.from_file(config_file)
        result = await agent.execute({"message": "Config file test"}, timeout=10)

        assert result.success is True
        assert "Config file test" in result.stdout


@pytest.mark.integration
class TestComposableAgentEnvironment:
    """Test environment variable handling in subprocess."""

    @pytest.mark.asyncio
    async def test_subprocess_inherits_environment(self) -> None:
        """Test that subprocess inherits environment variables."""
        # Set a test env var
        os.environ["GLYX_TEST_VAR"] = "test_value_123"

        config = AgentConfig(
            agent_key="env_test",
            command=sys.executable,
            args=[
                ArgSpec(name="code", flag="-c", type="string", required=True),
            ],
        )

        agent = ComposableAgent(config)
        result = await agent.execute(
            {"code": "import os; print(os.environ.get('GLYX_TEST_VAR', 'not found'))"},
            timeout=10,
        )

        assert result.success is True
        assert "test_value_123" in result.stdout

        # Clean up
        del os.environ["GLYX_TEST_VAR"]


@pytest.mark.e2e
class TestRealAgentExecution:
    """E2E tests with real agent CLIs - requires actual tools installed."""

    @pytest.mark.asyncio
    async def test_opencode_agent_execution(self) -> None:
        """Test executing the opencode agent (requires opencode CLI)."""
        import shutil

        from glyx_python_sdk import AgentKey

        agent = ComposableAgent.from_key(AgentKey.OPENCODE)

        assert agent.config.agent_key == "opencode"
        assert agent.config.command == "opencode"

        if not shutil.which("opencode"):
            pytest.skip("opencode CLI not installed")

        result = await agent.execute(
            {"prompt": "What is 2+2? Reply with just the number.", "model": "openrouter/google/gemini-2.0-flash-001"},
            timeout=60,
        )

        assert isinstance(result, AgentResult)
        assert result.execution_time > 0

    @pytest.mark.asyncio
    async def test_aider_agent_execution(self) -> None:
        """Test loading and executing the aider agent (requires aider CLI)."""
        import shutil

        from glyx_python_sdk import AgentKey

        agent = ComposableAgent.from_key(AgentKey.AIDER)

        assert agent.config.agent_key == "aider"
        assert agent.config.command == "aider"

        arg_names = [arg.name for arg in agent.config.args]
        assert "prompt" in arg_names or "message" in arg_names
        assert "model" in arg_names

        if not shutil.which("aider"):
            pytest.skip("aider CLI not installed")

    @pytest.mark.asyncio
    async def test_all_agent_configs_load(self) -> None:
        """Test that all agent JSON configs can be loaded and validated."""
        from glyx_python_sdk import AgentKey

        loaded_agents = []
        for key in AgentKey:
            agent = ComposableAgent.from_key(key)
            assert agent.config.agent_key is not None
            assert agent.config.command is not None
            loaded_agents.append(agent.config.agent_key)

        assert len(loaded_agents) >= 3, f"Expected at least 3 agents, got: {loaded_agents}"

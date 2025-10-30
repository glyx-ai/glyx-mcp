# Testing Plan for glyx-mcp Agent Abilities

**Document Version:** 1.0
**Date:** 2025-10-30
**Status:** Ready for Implementation

## Executive Summary

This plan addresses critical testing gaps in the glyx-mcp project. Current tests mock the entire execution layer, leaving core functionality untested. This plan introduces:

- **Pydantic-based validation** for type safety and runtime config validation
- **5 critical test suites** covering command building, subprocess execution, timeouts, config validation, and MCP integration
- **Structured result types** (AgentResult) for reliable error handling
- **Testing pyramid approach**: 60% unit, 30% integration, 10% E2E

**Expected Outcome:** 70% increase in test coverage (15% → 85%) with improved reliability and maintainability.

---

## Problem Statement

### Current State
- Only 2 test files with mocked execution (tests/test_tools.py)
- Core command building logic (composable_agent.py:73-94) has **zero test coverage**
- No validation for JSON agent configs
- No structured error handling (everything returns strings)
- No integration or E2E tests

### Risks
1. **Reliability Blind Spot:** Runtime failures from config errors or command building bugs
2. **Brittle Configs:** Typos in JSON configs only surface in production
3. **Debugging Difficulty:** String-based errors prevent programmatic error handling
4. **Regression Risk:** Changes to core logic can break silently

---

## Part 1: Pydantic Schema Validation

### Why Pydantic?
- ✅ Runtime validation with Python type hints
- ✅ Better error messages than jsonschema
- ✅ Parse JSON directly into typed models
- ✅ Already aligned with mypy strict mode
- ✅ Single source of truth for types and validation

### Implementation

#### Step 1.1: Add Pydantic Dependency

**File:** `pyproject.toml`

```toml
[project]
dependencies = [
    "fastmcp>=2.0.0",
    "pydantic>=2.0.0",
]
```

**Command:**
```bash
uv pip install pydantic
```

#### Step 1.2: Create Pydantic Models

**File:** `src/glyx_mcp/composable_agent.py`

Replace the current `AgentConfig` class (lines 24-50) with:

```python
from pydantic import BaseModel, Field, field_validator
from typing import Literal

class ArgSpec(BaseModel):
    """Specification for a single command-line argument."""
    flag: str = ""  # Empty string for positional args
    type: Literal["string", "bool", "int"] = "string"
    required: bool = False
    default: str | int | bool | None = None
    description: str = ""

    @field_validator('type')
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Ensure type is valid."""
        if v not in ["string", "bool", "int"]:
            raise ValueError(f"Invalid arg type: {v}")
        return v


class AgentConfig(BaseModel):
    """Agent configuration from JSON - validated with Pydantic."""
    agent_key: str
    command: str = Field(..., min_length=1)  # Must be non-empty
    args: dict[str, ArgSpec]
    description: str | None = None
    version: str | None = None
    capabilities: list[str] = Field(default_factory=list)

    @classmethod
    def from_file(cls, file_path: str | Path) -> "AgentConfig":
        """Load and validate config from JSON file."""
        with open(file_path) as f:
            data = json.load(f)

        agent_key = next(iter(data.keys()))
        agent_data = data[agent_key]
        agent_data["agent_key"] = agent_key

        # Pydantic validates automatically on instantiation
        return cls(**agent_data)
```

#### Step 1.3: Create AgentResult Model

Add this new class to `src/glyx_mcp/composable_agent.py`:

```python
from dataclasses import dataclass
from time import time

@dataclass
class AgentResult:
    """Structured result from agent execution."""
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    execution_time: float = 0.0
    command: list[str] = None  # The actual command executed (for debugging)

    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.exit_code == 0 and not self.timed_out

    @property
    def output(self) -> str:
        """Get combined output (for backward compatibility)."""
        result = self.stdout
        if self.stderr:
            result += f"\nSTDERR: {self.stderr}"
        return result
```

#### Step 1.4: Define Custom Exceptions

Add to `src/glyx_mcp/composable_agent.py`:

```python
class AgentError(Exception):
    """Base exception for agent errors."""
    pass

class AgentTimeoutError(AgentError):
    """Raised when agent execution times out."""
    pass

class AgentExecutionError(AgentError):
    """Raised when agent execution fails."""
    pass

class AgentConfigError(AgentError):
    """Raised when agent configuration is invalid."""
    pass
```

#### Step 1.5: Refactor execute() Method

Update `ComposableAgent.execute()` (lines 73-106) to return `AgentResult`:

```python
async def execute(self, task_config: dict[str, Any], timeout: int = 30) -> AgentResult:
    """Parse args and execute command, returning structured result."""
    start_time = time()
    cmd = [self.config.command]

    # Add all arguments with values from task_config or defaults
    for key, details in self.config.args.items():
        value = task_config.get(key, details.default)
        if value is not None:
            flag = details.flag
            if not flag:
                if details.type == "bool":
                    if value:
                        cmd.append(str(value))
                else:
                    cmd.append(str(value))
            else:
                if details.type == "bool":
                    if value:
                        cmd.append(flag)
                else:
                    cmd.extend([flag, str(value)])

    logger.info(f"Executing: {' '.join(cmd)}")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout
        )

        execution_time = time() - start_time

        return AgentResult(
            stdout=stdout.decode() if stdout else "",
            stderr=stderr.decode() if stderr else "",
            exit_code=process.returncode,
            timed_out=False,
            execution_time=execution_time,
            command=cmd
        )

    except asyncio.TimeoutError:
        execution_time = time() - start_time
        process.kill()
        await process.wait()
        raise AgentTimeoutError(
            f"Agent '{self.config.agent_key}' timed out after {timeout}s"
        )
    except Exception as e:
        execution_time = time() - start_time
        raise AgentExecutionError(
            f"Agent '{self.config.agent_key}' execution failed: {e}"
        ) from e
```

**Time Estimate:** 3 hours

---

## Part 2: Top 5 Critical Test Cases

### Test Priority Matrix

| # | Test Suite | Priority | Time | Impact | Coverage Gain |
|---|------------|----------|------|--------|---------------|
| 1 | Command Building | ⭐⭐⭐⭐⭐ | 2h | Critical | 25% |
| 2 | Subprocess Execution | ⭐⭐⭐⭐⭐ | 3h | Critical | 20% |
| 3 | Timeout Handling | ⭐⭐⭐⭐ | 2h | High | 10% |
| 4 | Config Validation | ⭐⭐⭐⭐ | 1h | High | 10% |
| 5 | MCP Integration | ⭐⭐⭐ | 2h | Medium | 5% |

---

### Test #1: Command Building with All Argument Types

**Priority:** ⭐⭐⭐⭐⭐ CRITICAL
**File:** `tests/test_composable_agent.py`
**Coverage Target:** Command construction logic (composable_agent.py:77-94)

#### Why Critical?
This is the core untested logic. Validates that JSON configs correctly translate to CLI commands.

#### Test Cases

```python
# tests/test_composable_agent.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from glyx_mcp.composable_agent import ComposableAgent, AgentConfig, ArgSpec, AgentResult

@pytest.mark.asyncio
async def test_command_building_with_mixed_argument_types():
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


@pytest.mark.asyncio
async def test_command_building_without_optional_args():
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


@pytest.mark.asyncio
async def test_command_building_with_positional_args():
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
```

**Validation Coverage:**
- ✅ Boolean flags are added without values
- ✅ String flags include their values
- ✅ Optional args with None are omitted
- ✅ Required args are present
- ✅ Positional args (empty flag) work correctly
- ✅ AgentResult structure is correct

**Time Estimate:** 2 hours

---

### Test #2: Subprocess Execution and Output Capture

**Priority:** ⭐⭐⭐⭐⭐ CRITICAL
**File:** `tests/test_integration.py`
**Coverage Target:** Process communication (composable_agent.py:97-106)

#### Why Critical?
Tests the actual subprocess communication logic with real process execution.

#### Test Cases

```python
# tests/test_integration.py
import pytest
import tempfile
import os
from pathlib import Path
from glyx_mcp.composable_agent import ComposableAgent, AgentConfig, ArgSpec

@pytest.mark.asyncio
async def test_subprocess_execution_with_mock_cli():
    """Test actual subprocess execution with a mock CLI script."""

    # Create a temporary mock CLI executable
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
        f.write("""#!/bin/bash
echo "stdout: received args: $@"
echo "stderr: warning message" >&2
exit 0
""")
        mock_cli_path = f.name

    try:
        # Make it executable
        os.chmod(mock_cli_path, 0o755)

        config = AgentConfig(
            agent_key="mock",
            command=mock_cli_path,
            args={
                "message": ArgSpec(flag="--msg", type="string"),
            }
        )

        agent = ComposableAgent(config)
        result = await agent.execute({"message": "hello"}, timeout=5)

        # Verify output capture
        assert "stdout: received args: --msg hello" in result.stdout
        assert "stderr: warning message" in result.stderr
        assert result.exit_code == 0
        assert result.success is True
        assert result.execution_time > 0
        assert "--msg" in result.command

    finally:
        os.unlink(mock_cli_path)


@pytest.mark.asyncio
async def test_subprocess_captures_stderr_on_failure():
    """Test that stderr is captured when process fails."""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
        f.write("""#!/bin/bash
echo "Error: invalid argument" >&2
exit 1
""")
        mock_cli_path = f.name

    try:
        os.chmod(mock_cli_path, 0o755)

        config = AgentConfig(
            agent_key="failing",
            command=mock_cli_path,
            args={}
        )

        agent = ComposableAgent(config)
        result = await agent.execute({}, timeout=5)

        assert result.exit_code == 1
        assert result.success is False
        assert "Error: invalid argument" in result.stderr

    finally:
        os.unlink(mock_cli_path)


@pytest.mark.asyncio
async def test_subprocess_execution_time_is_tracked():
    """Test that execution time is accurately measured."""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
        f.write("""#!/bin/bash
sleep 0.5
echo "done"
""")
        mock_cli_path = f.name

    try:
        os.chmod(mock_cli_path, 0o755)

        config = AgentConfig(
            agent_key="timed",
            command=mock_cli_path,
            args={}
        )

        agent = ComposableAgent(config)
        result = await agent.execute({}, timeout=10)

        # Should take at least 0.5s
        assert result.execution_time >= 0.5
        assert result.execution_time < 1.0  # But not too much longer

    finally:
        os.unlink(mock_cli_path)
```

**Validation Coverage:**
- ✅ Real subprocess spawning works
- ✅ Stdout and stderr are captured separately
- ✅ Exit codes are returned correctly
- ✅ Execution time is tracked
- ✅ Command is stored in result for debugging

**Time Estimate:** 3 hours

---

### Test #3: Timeout Handling

**Priority:** ⭐⭐⭐⭐ HIGH
**File:** `tests/test_composable_agent.py`
**Coverage Target:** Timeout logic (composable_agent.py:101)

#### Why High Priority?
Timeout logic is critical for preventing hung processes in production.

#### Test Cases

```python
# tests/test_composable_agent.py (continued)
import pytest
import asyncio
from glyx_mcp.composable_agent import AgentTimeoutError

@pytest.mark.asyncio
async def test_timeout_raises_custom_exception():
    """Test that long-running processes are killed and raise AgentTimeoutError."""

    # Create a mock CLI that sleeps longer than timeout
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
        f.write("""#!/bin/bash
sleep 10  # Sleep longer than our timeout
echo "This should not print"
""")
        mock_cli_path = f.name

    try:
        os.chmod(mock_cli_path, 0o755)

        config = AgentConfig(
            agent_key="slow",
            command=mock_cli_path,
            args={}
        )

        agent = ComposableAgent(config)

        # Should timeout after 1 second
        with pytest.raises(AgentTimeoutError) as exc_info:
            await agent.execute({}, timeout=1)

        assert "timed out after 1s" in str(exc_info.value)
        assert "slow" in str(exc_info.value)  # Agent key in error

    finally:
        os.unlink(mock_cli_path)


@pytest.mark.asyncio
async def test_fast_execution_does_not_timeout():
    """Test that quick processes complete before timeout."""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
        f.write("""#!/bin/bash
echo "quick response"
exit 0
""")
        mock_cli_path = f.name

    try:
        os.chmod(mock_cli_path, 0o755)

        config = AgentConfig(
            agent_key="fast",
            command=mock_cli_path,
            args={}
        )

        agent = ComposableAgent(config)
        result = await agent.execute({}, timeout=30)

        assert result.timed_out is False
        assert result.success is True
        assert result.execution_time < 1.0  # Should be subsecond

    finally:
        os.unlink(mock_cli_path)


@pytest.mark.asyncio
async def test_timeout_kills_process():
    """Test that timed-out processes are actually killed."""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
        f.write("""#!/bin/bash
# Create a file to prove we started
touch /tmp/test_process_started
sleep 100
# This should never execute
touch /tmp/test_process_completed
""")
        mock_cli_path = f.name

    try:
        os.chmod(mock_cli_path, 0o755)

        # Clean up any previous test artifacts
        if os.path.exists('/tmp/test_process_started'):
            os.unlink('/tmp/test_process_started')
        if os.path.exists('/tmp/test_process_completed'):
            os.unlink('/tmp/test_process_completed')

        config = AgentConfig(
            agent_key="killable",
            command=mock_cli_path,
            args={}
        )

        agent = ComposableAgent(config)

        with pytest.raises(AgentTimeoutError):
            await agent.execute({}, timeout=1)

        # Process should have started
        assert os.path.exists('/tmp/test_process_started')

        # But should NOT have completed (was killed)
        assert not os.path.exists('/tmp/test_process_completed')

    finally:
        os.unlink(mock_cli_path)
        # Cleanup
        if os.path.exists('/tmp/test_process_started'):
            os.unlink('/tmp/test_process_started')
```

**Validation Coverage:**
- ✅ Processes that exceed timeout are terminated
- ✅ Custom AgentTimeoutError is raised with context
- ✅ Quick processes complete successfully
- ✅ execution_time is tracked correctly
- ✅ Processes are actually killed (not just abandoned)

**Time Estimate:** 2 hours

---

### Test #4: Config Validation with Pydantic

**Priority:** ⭐⭐⭐⭐ HIGH
**File:** `tests/test_config_validation.py`
**Coverage Target:** Pydantic validation layer

#### Why High Priority?
Prevents malformed configs from causing runtime failures. Catches errors at startup.

#### Test Cases

```python
# tests/test_config_validation.py
import pytest
import json
from pydantic import ValidationError
from glyx_mcp.composable_agent import AgentConfig, ArgSpec

def test_valid_config_loads_successfully():
    """Test that a valid config passes Pydantic validation."""
    config = AgentConfig(
        agent_key="test",
        command="test_cli",
        args={
            "prompt": ArgSpec(flag="--message", type="string", required=True),
        },
        description="Test agent"
    )

    assert config.agent_key == "test"
    assert config.command == "test_cli"
    assert "prompt" in config.args
    assert config.args["prompt"].flag == "--message"


def test_missing_required_field_raises_validation_error():
    """Test that missing required fields are caught."""
    with pytest.raises(ValidationError) as exc_info:
        AgentConfig(
            agent_key="test",
            # Missing 'command' - required field
            args={}
        )

    error = exc_info.value
    assert "command" in str(error)
    assert "field required" in str(error).lower()


def test_empty_command_raises_validation_error():
    """Test that empty command string is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        AgentConfig(
            agent_key="test",
            command="",  # Empty string should fail min_length validation
            args={}
        )

    assert "command" in str(exc_info.value)


def test_invalid_arg_type_raises_validation_error():
    """Test that invalid argument types are caught."""
    with pytest.raises(ValidationError) as exc_info:
        ArgSpec(
            flag="--test",
            type="invalid_type",  # Should only be string/bool/int
            required=False
        )

    assert "type" in str(exc_info.value)


def test_arg_type_literal_enforcement():
    """Test that only valid arg types are accepted."""
    # Valid types should work
    valid_types = ["string", "bool", "int"]
    for arg_type in valid_types:
        arg = ArgSpec(flag="--test", type=arg_type)
        assert arg.type == arg_type

    # Invalid types should fail
    with pytest.raises(ValidationError):
        ArgSpec(flag="--test", type="float")


def test_config_from_file_validates_automatically(tmp_path):
    """Test that loading from file validates the config."""

    # Create a valid config file
    config_file = tmp_path / "valid.json"
    config_file.write_text(json.dumps({
        "test_agent": {
            "command": "test_cli",
            "args": {
                "prompt": {
                    "flag": "--message",
                    "type": "string",
                    "required": True
                }
            }
        }
    }))

    config = AgentConfig.from_file(config_file)
    assert config.agent_key == "test_agent"
    assert config.command == "test_cli"

    # Create an invalid config file (missing command)
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text(json.dumps({
        "bad_agent": {
            "args": {}
            # Missing 'command'
        }
    }))

    with pytest.raises(ValidationError):
        AgentConfig.from_file(invalid_file)


def test_all_existing_configs_are_valid():
    """Test that all existing agent config files are valid."""
    from pathlib import Path

    config_dir = Path(__file__).parent.parent / "src" / "glyx_mcp" / "config"

    if not config_dir.exists():
        pytest.skip("Config directory not found")

    config_files = list(config_dir.glob("*.json"))
    assert len(config_files) > 0, "No config files found"

    for config_file in config_files:
        # Should not raise ValidationError
        try:
            config = AgentConfig.from_file(config_file)
            assert config.agent_key is not None
            assert config.command is not None
            print(f"✓ {config_file.name} is valid")
        except ValidationError as e:
            pytest.fail(f"Config file {config_file.name} failed validation: {e}")


def test_config_with_capabilities():
    """Test that optional capabilities field works."""
    config = AgentConfig(
        agent_key="test",
        command="test_cli",
        args={},
        capabilities=["code_generation", "reasoning"]
    )

    assert len(config.capabilities) == 2
    assert "code_generation" in config.capabilities


def test_config_defaults():
    """Test that optional fields have correct defaults."""
    config = AgentConfig(
        agent_key="minimal",
        command="minimal_cli",
        args={}
    )

    assert config.description is None
    assert config.version is None
    assert config.capabilities == []
```

**Validation Coverage:**
- ✅ Pydantic catches missing required fields
- ✅ Invalid data types are rejected
- ✅ Empty/malformed values are caught
- ✅ Config files are validated on load
- ✅ All existing configs validate successfully

**Time Estimate:** 1 hour

---

### Test #5: MCP Tool Integration

**Priority:** ⭐⭐⭐ MEDIUM
**File:** `tests/test_mcp_integration.py`
**Coverage Target:** FastMCP tool wrappers

#### Why Medium Priority?
Validates that FastMCP tools are registered correctly and the MCP protocol works end-to-end.

#### Test Cases

```python
# tests/test_mcp_integration.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from glyx_mcp.tools.use_aider import use_aider
from glyx_mcp.tools.use_grok import use_grok
from glyx_mcp.composable_agent import AgentKey, AgentResult

@pytest.mark.asyncio
async def test_use_aider_tool_passes_correct_parameters():
    """Test that MCP tool wrapper passes parameters correctly."""

    mock_result = AgentResult(
        stdout="Code updated successfully",
        stderr="",
        exit_code=0,
        timed_out=False,
        execution_time=2.5,
        command=["aider", "--message", "test"]
    )

    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock(return_value=mock_result)

    with patch("glyx_mcp.tools.use_aider.ComposableAgent.from_key", return_value=mock_agent) as mock_from_key:
        result = await use_aider(
            prompt="Add docstring",
            files="src/main.py,src/utils.py",
            model="gpt-4o",
            read_files="README.md"
        )

        # Verify correct agent was selected
        mock_from_key.assert_called_once_with(AgentKey.AIDER)

        # Verify parameters were passed
        mock_agent.execute.assert_called_once()
        call_args = mock_agent.execute.call_args[0][0]
        assert call_args["prompt"] == "Add docstring"
        assert call_args["files"] == "src/main.py,src/utils.py"
        assert call_args["model"] == "gpt-4o"
        assert call_args["read_files"] == "README.md"

        # Verify timeout
        assert mock_agent.execute.call_args[1]["timeout"] == 300


@pytest.mark.asyncio
async def test_use_aider_with_defaults():
    """Test that aider tool applies correct defaults."""

    mock_result = AgentResult(
        stdout="done",
        stderr="",
        exit_code=0,
        timed_out=False,
        execution_time=1.0,
        command=["aider"]
    )

    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock(return_value=mock_result)

    with patch("glyx_mcp.tools.use_aider.ComposableAgent.from_key", return_value=mock_agent):
        # Call with only required params
        result = await use_aider(
            prompt="Test",
            files="test.py"
        )

        # Verify default model is used
        call_args = mock_agent.execute.call_args[0][0]
        assert call_args["model"] == "gpt-5"
        # read_files should not be in call_args if not provided
        assert "read_files" not in call_args


@pytest.mark.asyncio
async def test_use_grok_tool_with_default_model():
    """Test that grok tool uses default model when not specified."""

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
        result = await use_grok(prompt="What is the meaning of life?")

        # Verify correct agent selected
        mock_from_key.assert_called_once_with(AgentKey.GROK)

        # Verify default model is used
        call_args = mock_agent.execute.call_args[0][0]
        assert call_args["model"] == "openrouter/x-ai/grok-4-fast"


@pytest.mark.asyncio
async def test_use_grok_with_custom_model():
    """Test that grok tool accepts custom model parameter."""

    mock_result = AgentResult(
        stdout="response",
        stderr="",
        exit_code=0,
        timed_out=False,
        execution_time=1.0,
        command=["opencode"]
    )

    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock(return_value=mock_result)

    with patch("glyx_mcp.tools.use_grok.ComposableAgent.from_key", return_value=mock_agent):
        result = await use_grok(
            prompt="Test",
            model="openrouter/x-ai/grok-2-latest"
        )

        call_args = mock_agent.execute.call_args[0][0]
        assert call_args["model"] == "openrouter/x-ai/grok-2-latest"


def test_mcp_server_registers_expected_tools():
    """Test that FastMCP server registers all expected tools."""
    from glyx_mcp.server import mcp

    # This test depends on FastMCP's API for inspecting registered tools
    # Adjust based on FastMCP's actual API

    # Get list of registered tools
    # Note: FastMCP may expose this differently
    registered_tools = [name for name, _ in mcp._tool_registry.items()] if hasattr(mcp, '_tool_registry') else []

    # Verify expected tools are registered
    assert "use_aider" in registered_tools
    assert "use_grok" in registered_tools


@pytest.mark.asyncio
async def test_tool_error_handling():
    """Test that tool wrappers handle agent errors gracefully."""

    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock(side_effect=Exception("Agent crashed"))

    with patch("glyx_mcp.tools.use_aider.ComposableAgent.from_key", return_value=mock_agent):
        # Should not crash, should propagate exception
        with pytest.raises(Exception) as exc_info:
            await use_aider(prompt="test", files="test.py")

        assert "Agent crashed" in str(exc_info.value)
```

**Validation Coverage:**
- ✅ MCP tool wrappers call ComposableAgent correctly
- ✅ Default parameter values are applied
- ✅ Custom parameters override defaults
- ✅ Tools are registered with FastMCP server
- ✅ Error handling works correctly

**Time Estimate:** 2 hours

---

## Part 3: Implementation Roadmap

### Phase 1: Foundation (Week 1)

**Goal:** Add Pydantic validation and core data structures

**Tasks:**
1. ✅ Add Pydantic to dependencies (`pyproject.toml`)
2. ✅ Create `ArgSpec` Pydantic model
3. ✅ Refactor `AgentConfig` to use Pydantic
4. ✅ Create `AgentResult` dataclass
5. ✅ Define custom exceptions (`AgentTimeoutError`, etc.)
6. ✅ Refactor `ComposableAgent.execute()` to return `AgentResult`
7. ✅ Update MCP tools to handle `AgentResult`

**Deliverables:**
- Pydantic models in `composable_agent.py`
- All agent configs validate on startup
- Structured error types
- Updated tool wrappers

**Time:** ~1 day

---

### Phase 2: Critical Tests (Week 1-2)

**Goal:** Add tests for core untested logic

**Tasks:**
1. ✅ Implement Test #1 (Command Building) - 2 hours
2. ✅ Implement Test #2 (Subprocess Execution) - 3 hours
3. ✅ Implement Test #3 (Timeout Handling) - 2 hours
4. ✅ Implement Test #4 (Config Validation) - 1 hour

**Deliverables:**
- `tests/test_composable_agent.py` with 10+ test cases
- `tests/test_integration.py` with mock CLI executables
- `tests/test_config_validation.py` with Pydantic tests
- Coverage increase: 15% → 65%

**Time:** ~1 day

---

### Phase 3: MCP Integration (Week 2)

**Goal:** Validate MCP protocol integration

**Tasks:**
1. ✅ Implement Test #5 (MCP Integration) - 2 hours
2. ✅ Add tests for prompt functions (`prompts.py`)
3. ✅ Test FastMCP server initialization
4. ✅ Validate tool schemas

**Deliverables:**
- `tests/test_mcp_integration.py`
- `tests/test_prompts.py`
- Coverage increase: 65% → 75%

**Time:** ~4 hours

---

### Phase 4: E2E & CI/CD (Week 2-3)

**Goal:** Add end-to-end tests and automation

**Tasks:**
1. ✅ Create Docker Compose test harness
2. ✅ Write E2E tests with real agents (optional/slow)
3. ✅ Set up GitHub Actions CI pipeline
4. ✅ Add coverage reporting
5. ✅ Add test documentation

**Deliverables:**
- `tests/test_e2e.py` (optional - requires real CLIs)
- `.github/workflows/test.yml`
- Coverage report integration
- Coverage increase: 75% → 85%

**Time:** ~1 day

---

## Part 4: Quick Wins (Implement Immediately)

### Quick Win #1: Add Pydantic Dependency
```bash
# Add to pyproject.toml
[project]
dependencies = [
    "fastmcp>=2.0.0",
    "pydantic>=2.0.0",
]

# Install
uv pip install pydantic
```

**Time:** 5 minutes

---

### Quick Win #2: Validate All Configs on Startup

Add to `src/glyx_mcp/server.py`:

```python
def validate_all_configs() -> None:
    """Validate all agent configs on startup."""
    from pathlib import Path
    from glyx_mcp.composable_agent import AgentConfig

    config_dir = Path(__file__).parent / "config"
    logger.info(f"Validating agent configs in {config_dir}")

    for config_file in config_dir.glob("*.json"):
        try:
            config = AgentConfig.from_file(config_file)
            logger.info(f"✓ {config.agent_key} config is valid")
        except Exception as e:
            logger.error(f"✗ {config_file.name} validation failed: {e}")
            raise

# Call on server startup
validate_all_configs()
```

**Time:** 10 minutes

---

### Quick Win #3: Centralize Timeout Configuration

Add to `src/glyx_mcp/composable_agent.py`:

```python
# Default timeout constant
DEFAULT_AGENT_TIMEOUT = 300  # 5 minutes

class AgentConfig(BaseModel):
    # ... existing fields ...
    timeout: int = DEFAULT_AGENT_TIMEOUT  # Allow per-agent timeout override
```

Update all tool calls to use `config.timeout`:
```python
await ComposableAgent.from_key(AgentKey.AIDER).execute(
    task_config,
    timeout=agent.config.timeout  # Use config timeout
)
```

**Time:** 15 minutes

---

### Quick Win #4: Improve Logging

Update `ComposableAgent.execute()`:

```python
async def execute(self, task_config: dict, timeout: int = 30) -> AgentResult:
    start_time = time()
    cmd = self._build_command(task_config)  # Extract to method

    # Log BEFORE execution with full context
    logger.info(
        f"Executing agent '{self.config.agent_key}'",
        extra={
            "agent": self.config.agent_key,
            "command": " ".join(cmd),
            "timeout": timeout,
            "task_config": task_config
        }
    )

    # ... execution logic ...

    # Log AFTER execution
    logger.info(
        f"Agent '{self.config.agent_key}' completed",
        extra={
            "agent": self.config.agent_key,
            "exit_code": result.exit_code,
            "execution_time": result.execution_time,
            "success": result.success
        }
    )
```

**Time:** 20 minutes

---

## Part 5: Success Metrics

### Coverage Targets

| Phase | Coverage | Test Count | Files Covered |
|-------|----------|------------|---------------|
| Current | ~15% | 2 tests | tools only |
| Phase 1 | ~25% | 5 tests | + config validation |
| Phase 2 | ~65% | 20+ tests | + core logic |
| Phase 3 | ~75% | 30+ tests | + MCP integration |
| Phase 4 | ~85% | 35+ tests | + E2E (optional) |

### Quality Metrics

**Before:**
- ❌ Core logic untested
- ❌ No config validation
- ❌ String-based errors
- ❌ No integration tests
- ❌ No CI/CD

**After:**
- ✅ 85% test coverage
- ✅ Pydantic validation
- ✅ Structured errors
- ✅ Integration + E2E tests
- ✅ Automated CI/CD

---

## Part 6: Risk Mitigation

### Backward Compatibility

**Risk:** Changing `execute()` to return `AgentResult` breaks existing code.

**Mitigation:**
1. Add `output` property to `AgentResult` for backward compatibility:
   ```python
   @property
   def output(self) -> str:
       """Backward compatible string output."""
       return self.stdout + ("\nSTDERR: " + self.stderr if self.stderr else "")
   ```

2. Update all tool wrappers to return `result.output` initially
3. Gradually migrate to structured results

---

### Test Maintenance

**Risk:** Mock CLI tests are fragile and OS-dependent.

**Mitigation:**
1. Use `pytest.mark.skipif(sys.platform == "win32")` for bash scripts
2. Create Python-based mock CLIs for cross-platform compatibility
3. Use Docker for E2E tests to ensure consistency

---

### Performance

**Risk:** Adding validation might slow down agent execution.

**Mitigation:**
1. Pydantic validation is fast (~microseconds for simple models)
2. Cache loaded configs (don't reload from disk each time)
3. Benchmark before/after to measure impact

---

## Part 7: Next Steps

### Immediate Actions (Today)

1. **Add Pydantic dependency** and refactor `AgentConfig`
2. **Implement AgentResult** dataclass
3. **Write Test #1** (Command Building) - highest ROI

### This Week

4. **Complete Tests #2-4** (Subprocess, Timeout, Config)
5. **Update all tool wrappers** to handle structured results
6. **Set up pytest configuration**

### Next Week

7. **Implement Test #5** (MCP Integration)
8. **Add GitHub Actions CI**
9. **Write documentation** for testing approach

---

## Appendix A: Testing Tools & Configuration

### pytest Configuration

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto

# Coverage settings
addopts =
    --verbose
    --cov=src/glyx_mcp
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=70

# Markers
markers =
    integration: Integration tests (require mock executables)
    e2e: End-to-end tests (require real agent CLIs)
    slow: Slow tests (can skip in quick runs)
```

### Coverage Configuration

Create `.coveragerc`:

```ini
[run]
source = src/glyx_mcp
omit =
    */tests/*
    */test_*.py
    */__pycache__/*

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
```

### GitHub Actions Workflow

Create `.github/workflows/test.yml`:

```yaml
name: Tests

on:
  push:
    branches: [ master, main ]
  pull_request:
    branches: [ master, main ]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Install uv
      run: curl -LsSf https://astral.sh/uv/install.sh | sh

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        uv pip install --system -e ".[dev]"

    - name: Run tests
      run: |
        pytest --cov --cov-report=xml

    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

---

## Appendix B: Test File Structure

```
glyx-mcp/
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Shared fixtures
│   ├── test_composable_agent.py    # Test #1 & #3
│   ├── test_integration.py         # Test #2
│   ├── test_config_validation.py   # Test #4
│   ├── test_mcp_integration.py     # Test #5
│   ├── test_prompts.py            # Prompt function tests
│   ├── test_e2e.py                # E2E tests (optional)
│   └── fixtures/
│       ├── mock_agents/           # Mock CLI executables
│       │   ├── mock_aider.sh
│       │   ├── mock_grok.sh
│       │   └── mock_slow.sh
│       └── test_configs/          # Test config files
│           ├── valid_agent.json
│           └── invalid_agent.json
```

---

## Document Revision History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2025-10-30 | Initial plan | Analysis Team |

---

## Contact & Questions

For questions about this testing plan:
- Open an issue in the GitHub repository
- Review the analysis in this conversation thread
- Consult the glyx-mcp documentation

**Status:** ✅ Ready for implementation

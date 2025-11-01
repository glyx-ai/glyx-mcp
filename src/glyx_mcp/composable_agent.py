"""ComposableAgent - Simple JSON to CLI wrapper."""

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from time import time
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from langfuse import get_client

logger = logging.getLogger(__name__)


# Custom Exceptions
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


class AgentKey(str, Enum):
    GEMINI = "gemini"
    CLAUDE = "claude"
    AIDER = "aider"
    CODEX = "codex"
    OPENCODE = "opencode"
    GROK = "grok"
    DEEPSEEK_R1 = "deepseek_r1"
    KIMI_K2 = "kimi_k2"


@dataclass
class AgentResult:
    """Structured result from agent execution."""
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    execution_time: float = 0.0
    command: list[str] | None = None

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


class TaskConfig(BaseModel):
    """Task configuration for agent execution - validated with Pydantic."""
    prompt: str = Field(..., min_length=1)  # Always required
    model: str = "gpt-5"  # Default model
    files: str | None = None
    read_files: str | None = None
    working_dir: str | None = None
    max_turns: int | None = None

    model_config = {"extra": "allow"}  # Allow additional fields for extensibility


class ComposableAgent:
    """Dead simple JSON-driven CLI wrapper."""

    def __init__(self, config: AgentConfig):
        """Initialize with AgentConfig."""
        self.config = config

    @classmethod
    def from_file(cls, file_path: str | Path) -> "ComposableAgent":
        """Create agent from config file."""
        config = AgentConfig.from_file(file_path)
        return cls(config)

    @classmethod
    def from_key(cls, key: AgentKey) -> "ComposableAgent":
        """Create agent from a key."""
        config_dir = Path(__file__).parent / "config"
        file_path = config_dir / f"{key.value}.json"
        return cls.from_file(file_path)

    async def execute(self, task_config: dict[str, Any], timeout: int = 30) -> AgentResult:
        """Parse args and execute command, returning structured result."""
        start_time = time()
        cmd = [self.config.command]

        # Add all arguments with values from task_config or defaults
        for key, arg_spec in self.config.args.items():
            value = task_config.get(key, arg_spec.default)
            if value is not None:
                flag = arg_spec.flag
                if not flag:
                    if arg_spec.type == "bool":
                        if value:
                            cmd.append(str(value))
                    else:
                        cmd.append(str(value))
                else:
                    if arg_spec.type == "bool":
                        if value:
                            cmd.append(flag)
                    else:
                        cmd.extend([flag, str(value)])

        logger.info(
            f"Executing agent '{self.config.agent_key}'",
            extra={
                "agent": self.config.agent_key,
                "command": " ".join(cmd),
                "timeout": timeout,
            }
        )

        # Start Langfuse span for tracing
        langfuse = get_client()
        with langfuse.start_as_current_span(name=f"agent_{self.config.agent_key}") as span:
            span.update(
                input={
                    "agent": self.config.agent_key,
                    "command": " ".join(cmd),
                    "task_config": task_config,
                    "timeout": timeout,
                }
            )

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

                result = AgentResult(
                    stdout=stdout.decode() if stdout else "",
                    stderr=stderr.decode() if stderr else "",
                    exit_code=process.returncode if process.returncode is not None else -1,
                    timed_out=False,
                    execution_time=execution_time,
                    command=cmd
                )

                logger.info(
                    f"Agent '{self.config.agent_key}' completed",
                    extra={
                        "agent": self.config.agent_key,
                        "exit_code": result.exit_code,
                        "execution_time": result.execution_time,
                        "success": result.success
                    }
                )

                # Update span with output
                span.update(
                    output={
                        "exit_code": result.exit_code,
                        "execution_time": result.execution_time,
                        "success": result.success,
                        "stdout_length": len(result.stdout),
                        "stderr_length": len(result.stderr),
                    }
                )

                return result

            except asyncio.TimeoutError:
                execution_time = time() - start_time
                process.kill()
                await process.wait()

                span.update(
                    output={"error": "timeout", "execution_time": execution_time}
                )

                raise AgentTimeoutError(
                    f"Agent '{self.config.agent_key}' timed out after {timeout}s"
                )
            except Exception as e:
                execution_time = time() - start_time

                span.update(
                    output={"error": str(e), "execution_time": execution_time}
                )

                raise AgentExecutionError(
                    f"Agent '{self.config.agent_key}' execution failed: {e}"
                ) from e

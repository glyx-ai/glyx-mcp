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
    SHOT_SCRAPER = "shot_scraper"


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
        logger.info(f"[AGENT EXECUTE] Starting execution for {self.config.agent_key}")
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

        logger.info(f"[AGENT CMD] Executing: {' '.join(cmd)}")

        subprocess_start = time()
        logger.info(f"[AGENT SUBPROCESS] Creating subprocess...")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,  # Close stdin to prevent hanging
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        logger.info(f"[AGENT SUBPROCESS] Created in {time() - subprocess_start:.2f}s, waiting for output...")

        communicate_start = time()
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout
        )
        logger.info(f"[AGENT COMMUNICATE] Done in {time() - communicate_start:.2f}s")

        execution_time = time() - start_time

        result = AgentResult(
            stdout=stdout.decode() if stdout else "",
            stderr=stderr.decode() if stderr else "",
            exit_code=process.returncode if process.returncode is not None else -1,
            timed_out=False,
            execution_time=execution_time,
            command=cmd
        )

        logger.info(f"[AGENT RESULT] Completed in {execution_time:.2f}s (exit={result.exit_code}, stdout={len(result.stdout)} bytes, stderr={len(result.stderr)} bytes)")

        return result

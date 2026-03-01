"""Agent-specific types for glyx-python-sdk."""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentKey(str, Enum):
    """Known agent keys with JSON configs."""

    CURSOR = "cursor"
    GEMINI = "gemini"
    CLAUDE = "claude"
    AIDER = "aider"
    CODEX = "codex"
    OPENCODE = "opencode"
    GROK = "grok"
    DEEPSEEK_R1 = "deepseek_r1"
    KIMI_K2 = "kimi_k2"


# Canonical mapping from agent_type strings (as stored in agent_tasks) to AgentKey.
# Shared by LocalExecutor, CloudExecutor, and any future executor.
AGENT_KEY_MAP: dict[str, AgentKey] = {
    "claude": AgentKey.CLAUDE,
    "claude-code": AgentKey.CLAUDE,
    "cursor": AgentKey.CURSOR,
    "codex": AgentKey.CODEX,
    "aider": AgentKey.AIDER,
    "gemini": AgentKey.GEMINI,
    "opencode": AgentKey.OPENCODE,
    "grok": AgentKey.GROK,
}


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
    """Specification for a single command-line argument with full CLI feature support."""

    model_config = ConfigDict(strict=True)

    name: str
    flag: str = ""
    type: Literal["string", "bool", "int", "float"] = "string"
    required: bool = False
    default: str = ""
    description: str = ""
    short_flag: str = ""
    positional: bool = False
    position: int = 0
    choices: list[str] = Field(default_factory=list)
    variadic: bool = False
    env_var: str = ""
    implicit_bool: bool = True
    exclusive_group: str = ""


class SubcommandSpec(BaseModel):
    """A subcommand within a CLI tool."""

    model_config = ConfigDict(strict=True)

    name: str
    command: str
    args: list[ArgSpec] = Field(default_factory=list)
    description: str = ""


class AgentConfig(BaseModel):
    """Agent configuration from JSON with subcommand support."""

    model_config = ConfigDict(strict=True)

    agent_key: str
    command: str = Field(..., min_length=1)
    args: list[ArgSpec] = Field(default_factory=list)
    description: str = ""
    version: str = ""
    capabilities: list[str] = Field(default_factory=list)
    subcommands: list[SubcommandSpec] = Field(default_factory=list)
    global_args: list[ArgSpec] = Field(default_factory=list)

    @classmethod
    def from_file(cls, file_path: str | Path) -> "AgentConfig":
        """Load and validate config from JSON file."""
        with open(file_path) as f:
            data = json.load(f)

        agent_key = next(iter(data.keys()))
        agent_data = data[agent_key]
        agent_data["agent_key"] = agent_key

        if "args" in agent_data and isinstance(agent_data["args"], dict):
            agent_data["args"] = [{"name": name, **spec} for name, spec in agent_data["args"].items()]

        return cls(**agent_data)


class TaskConfig(BaseModel):
    """Task configuration for agent execution."""

    prompt: str = Field(..., min_length=1)
    model: str = "gpt-5"
    files: str | None = None
    read_files: str | None = None
    working_dir: str | None = None
    max_turns: int | None = None

    model_config = {"extra": "allow"}


class Event(BaseModel):
    """Generic event for the activity feed."""

    orchestration_id: str
    type: str
    actor: str = "system"
    content: str
    metadata: dict[str, Any] | None = None

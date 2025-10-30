"""ComposableAgent - Simple JSON to CLI wrapper."""

import asyncio
import json
import logging
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AgentKey(str, Enum):
    GEMINI = "gemini"
    CLAUDE = "claude"
    AIDER = "aider"
    CODEX = "codex"
    OPENCODE = "opencode"
    GROK = "grok"
    DEEPSEEK_R1 = "deepseek_r1"
    KIMI_K2 = "kimi_k2"


class AgentConfig:
    """Agent configuration from JSON."""

    def __init__(
        self,
        agent_key: str,
        command: str,
        args: dict[str, dict[str, Any]],
        description: str | None = None,
        **kwargs: Any,
    ):
        self.agent_key = agent_key
        self.command = command
        self.args = args
        self.description = description

    @classmethod
    def from_file(cls, file_path: str | Path) -> "AgentConfig":
        """Load config from JSON file."""
        with open(file_path) as f:
            data = json.load(f)

        agent_key = next(iter(data.keys()))
        agent_data = data[agent_key]
        agent_data["agent_key"] = agent_key

        return cls(**agent_data)


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

    async def execute(self, task_config: dict[str, Any], timeout: int = 30) -> str:
        """Parse args and execute command."""
        cmd = [self.config.command]

        # Add all arguments with values from task_config or defaults
        for key, details in self.config.args.items():
            value = task_config.get(key, details.get("default"))
            if value is not None:
                flag = details.get("flag")
                if not flag:
                    if details.get("type") == "bool":
                        if value:
                            cmd.append(str(value))
                    else:
                        cmd.append(str(value))
                else:
                    if details.get("type") == "bool":
                        if value:
                            cmd.append(flag)
                    else:
                        cmd.extend([flag, str(value)])

        logger.info(f"Executing: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

        result = stdout.decode() if stdout else ""
        if stderr:
            result += f"\nSTDERR: {stderr.decode()}"
        return result

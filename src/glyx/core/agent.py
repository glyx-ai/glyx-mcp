"""ComposableAgent - Simple JSON to CLI wrapper."""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from time import time
from typing import Any, AsyncGenerator, Literal

from pydantic import BaseModel, Field, field_validator

from glyx.mcp.realtime import broadcast_event

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
    CURSOR = "cursor"
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
    """JSON-driven CLI wrapper for AI agents.

    Real-time update mechanisms:
    - broadcast_event(): WebSocket push to connected clients
      Used by: Web UI (glyx dashboard), Browser Extension
    - execute_stream(): Async generator yielding NDJSON events
      Used by: MCP Server HTTP endpoints (/stream/cursor)
    - ctx.info(): FastMCP context progress reporting
      Used by: Claude Code MCP integration
    """

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
        config_dir = Path(__file__).parent.parent.parent.parent / "agents"
        file_path = config_dir / f"{key.value}.json"
        return cls.from_file(file_path)

    async def execute(self, task_config: dict[str, Any], timeout: int = 30, ctx=None) -> AgentResult:
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

        await broadcast_event(
            "agent.start",
            {"agent_key": self.config.agent_key, "command": cmd, "timeout_s": timeout},
        )

        try:
            subprocess_start = time()
            logger.info(f"[AGENT SUBPROCESS] Creating subprocess...")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            logger.info(f"[AGENT SUBPROCESS] Created in {time() - subprocess_start:.2f}s, waiting for output...")

            stdout_lines = []
            stderr_lines = []

            async def read_stream(stream, lines_list, is_stderr=False):
                """Read stream line-by-line and emit via ctx.info()."""
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode().rstrip()
                    lines_list.append(decoded)
                    if ctx and decoded.strip():
                        try:
                            prefix = "stderr: " if is_stderr else ""
                            await ctx.info(f"{prefix}{decoded}")
                        except Exception as e:
                            logger.warning(f"Failed to emit progress: {e}")

            communicate_start = time()
            await asyncio.wait_for(
                asyncio.gather(
                    read_stream(process.stdout, stdout_lines, is_stderr=False),
                    read_stream(process.stderr, stderr_lines, is_stderr=True),
                    process.wait()
                ),
                timeout=timeout
            )
            logger.info(f"[AGENT COMMUNICATE] Done in {time() - communicate_start:.2f}s")

            execution_time = time() - start_time

            result = AgentResult(
                stdout="\n".join(stdout_lines),
                stderr="\n".join(stderr_lines),
                exit_code=process.returncode if process.returncode is not None else -1,
                timed_out=False,
                execution_time=execution_time,
                command=cmd
            )

            logger.info(f"[AGENT RESULT] Completed in {execution_time:.2f}s (exit={result.exit_code}, stdout={len(result.stdout)} bytes, stderr={len(result.stderr)} bytes)")

            await broadcast_event(
                "agent.finish",
                {
                    "agent_key": self.config.agent_key,
                    "exit_code": result.exit_code,
                    "execution_time_s": execution_time,
                    "stdout_bytes": len(result.stdout),
                    "stderr_bytes": len(result.stderr),
                },
            )

            return result

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            logger.warning(f"[AGENT TIMEOUT] Process killed after {timeout}s")
            await broadcast_event(
                "agent.timeout",
                {"agent_key": self.config.agent_key, "timeout_s": timeout, "command": cmd},
            )
            raise

        except Exception as e:
            await broadcast_event(
                "agent.error",
                {"agent_key": self.config.agent_key, "error": str(e), "command": cmd},
            )
            raise

    async def execute_stream(self, task_config: dict[str, Any], timeout: int = 30) -> AsyncGenerator[dict[str, Any], None]:
        """Execute command and yield events in real-time (NDJSON parsing)."""
        start_time = time()
        logger.info(f"[AGENT STREAM] Starting streaming execution for {self.config.agent_key}")

        cmd = [self.config.command]
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

        logger.info(f"[AGENT STREAM CMD] {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        event_queue = asyncio.Queue()
        process_done = asyncio.Event()

        async def stream_stdout():
            """Parse NDJSON from stdout and queue events."""
            if process.stdout:
                async for line in process.stdout:
                    line_text = line.decode().rstrip()
                    if line_text:
                        try:
                            event = json.loads(line_text)
                            await event_queue.put({
                                "type": "agent_event",
                                "event": event,
                                "timestamp": datetime.now().isoformat()
                            })
                            logger.info(f"[AGENT STREAM EVENT] {event.get('type', 'unknown')}")
                        except json.JSONDecodeError:
                            await event_queue.put({
                                "type": "agent_output",
                                "content": line_text,
                                "timestamp": datetime.now().isoformat()
                            })
                            logger.info(f"[AGENT STREAM OUTPUT] {line_text[:100]}")

        async def stream_stderr():
            """Stream stderr as error events."""
            if process.stderr:
                async for line in process.stderr:
                    line_text = line.decode().rstrip()
                    if line_text:
                        await event_queue.put({
                            "type": "agent_error",
                            "content": line_text,
                            "timestamp": datetime.now().isoformat()
                        })
                        logger.warning(f"[AGENT STREAM ERROR] {line_text[:100]}")

        async def wait_for_process():
            """Wait for process completion and signal done."""
            await process.wait()
            process_done.set()

        tasks = [
            asyncio.create_task(stream_stdout()),
            asyncio.create_task(stream_stderr()),
            asyncio.create_task(wait_for_process())
        ]

        try:
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                    yield event
                except asyncio.TimeoutError:
                    if process_done.is_set() and event_queue.empty():
                        break

            execution_time = time() - start_time
            yield {
                "type": "agent_complete",
                "exit_code": process.returncode if process.returncode is not None else -1,
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat()
            }
            logger.info(f"[AGENT STREAM COMPLETE] {execution_time:.2f}s (exit={process.returncode})")

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            yield {
                "type": "agent_timeout",
                "timeout": timeout,
                "timestamp": datetime.now().isoformat()
            }
            logger.error(f"[AGENT STREAM TIMEOUT] Killed after {timeout}s")
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()

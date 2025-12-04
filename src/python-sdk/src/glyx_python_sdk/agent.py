"""ComposableAgent - Simple JSON to CLI wrapper."""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from time import time
from typing import Any, AsyncGenerator, Literal

from pydantic import BaseModel, Field, field_validator
from supabase import create_client

from glyx_python_sdk.models.cursor import (
    BaseCursorEvent,
    CursorAssistantEvent,
    CursorResultEvent,
    CursorThinkingEvent,
    CursorToolCallEvent,
    parse_cursor_event,
)
from glyx_python_sdk.models.response import (
    BaseResponseEvent,
    parse_response_event,
    summarize_tool_activity,
)
from glyx_python_sdk.settings import settings
from glyx_python_sdk.websocket_manager import broadcast_event

logger = logging.getLogger(__name__)


class Event(BaseModel):
    """Generic event for the activity feed."""

    org_id: str
    org_name: str | None = None
    type: str
    actor: str = "system"
    content: str
    metadata: dict[str, Any] | None = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


def get_supabase():
    """Get Supabase client for event creation."""
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")
    return create_client(settings.supabase_url, settings.supabase_anon_key)


async def create_event(
    org_id: str,
    type: str,
    content: str,
    org_name: str | None = None,
    actor: str = "system",
    metadata: dict[str, Any] | None = None,
) -> Event:
    """Create an event record in Supabase."""
    event = Event(
        org_id=org_id,
        org_name=org_name,
        type=type,
        actor=actor,
        content=content,
        metadata=metadata,
    )
    client = get_supabase()
    client.table("events").insert(event.model_dump()).execute()
    logger.info(f"[EVENT] Created: {event.type} - {event.content[:50]}")
    return event


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

    @field_validator("type")
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
        # Get agents directory - now in same package root
        config_dir = Path(__file__).parent.parent / "agents"
        file_path = config_dir / f"{key.value}.json"
        return cls.from_file(file_path)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ComposableAgent":
        """Create agent from dictionary (e.g., Supabase row).

        Args:
            data: Dictionary with agent_key, command, args, etc.

        Returns:
            ComposableAgent instance.
        """
        args = {k: ArgSpec(**v) for k, v in data["args"].items()}
        config = AgentConfig(
            agent_key=data["agent_key"],
            command=data["command"],
            args=args,
            description=data.get("description"),
            version=data.get("version"),
            capabilities=data.get("capabilities", []),
        )
        return cls(config)

    async def execute(self, task_config: dict[str, Any], timeout: int = 30, ctx=None) -> AgentResult:
        """Parse args and execute command, returning structured result."""
        start_time = time()
        model = task_config.get("model", "gpt-5")
        logger.info(f"[AGENT EXECUTE] Starting execution for {self.config.agent_key} (model={model})")
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

        logger.info(f"[AGENT CMD] Executing: {' '.join(cmd)} (model={model})")

        await broadcast_event(
            "agent.start",
            {"agent_key": self.config.agent_key, "command": cmd, "timeout_s": timeout, "model": model},
        )

        subprocess_start = time()
        logger.info(f"[AGENT SUBPROCESS] Creating subprocess...")
        process = await asyncio.create_subprocess_exec(
            *cmd, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
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
                    prefix = "stderr: " if is_stderr else ""
                    await ctx.info(f"{prefix}{decoded}")

        communicate_start = time()
        await asyncio.wait_for(
            asyncio.gather(
                read_stream(process.stdout, stdout_lines, is_stderr=False),
                read_stream(process.stderr, stderr_lines, is_stderr=True),
                process.wait(),
            ),
            timeout=timeout,
        )
        logger.info(f"[AGENT COMMUNICATE] Done in {time() - communicate_start:.2f}s")

        execution_time = time() - start_time

        result = AgentResult(
            stdout="\n".join(stdout_lines),
            stderr="\n".join(stderr_lines),
            exit_code=process.returncode if process.returncode is not None else -1,
            timed_out=False,
            execution_time=execution_time,
            command=cmd,
        )

        logger.info(
            f"[AGENT RESULT] Completed in {execution_time:.2f}s (model={model}, exit={result.exit_code}, stdout={len(result.stdout)} bytes, stderr={len(result.stderr)} bytes)"
        )

        await broadcast_event(
            "agent.finish",
            {
                "agent_key": self.config.agent_key,
                "model": model,
                "exit_code": result.exit_code,
                "execution_time_s": execution_time,
                "stdout_bytes": len(result.stdout),
                "stderr_bytes": len(result.stderr),
            },
        )

        return result

    def _event_to_event(
        self,
        event: BaseCursorEvent,
        org_id: str,
        org_name: str | None,
        thinking_buffer: list[str],
        thinking_start: float | None,
    ) -> Event | tuple[str, ...] | None:
        """Convert cursor event to Event. Returns tuple for stateful thinking events."""
        match event:
            case CursorToolCallEvent():
                return Event(
                    org_id=org_id,
                    org_name=org_name,
                    content=event.tool_name,
                    type="tool_call",
                    actor=self.config.agent_key,
                    metadata={"tool_name": event.tool_name, "file_path": event.preview},
                )
            case CursorThinkingEvent(subtype="delta", text=text):
                return ("buffer_thinking", text)
            case CursorThinkingEvent(subtype="completed") if thinking_buffer:
                duration = time() - thinking_start if thinking_start else 0
                return ("flush_thinking", "".join(thinking_buffer), duration)
            case CursorAssistantEvent(message=msg):
                raw_content = msg.get("content", []) if isinstance(msg, dict) else []
                content = "".join(block.get("text", "") for block in raw_content if isinstance(block, dict))
                return (
                    Event(
                        org_id=org_id,
                        org_name=org_name,
                        content=content,
                        type="message",
                        actor=self.config.agent_key,
                    )
                    if content
                    else None
                )
            case CursorResultEvent(is_error=is_err, result=result, duration_ms=ms):
                return Event(
                    org_id=org_id,
                    org_name=org_name,
                    content=result,
                    type="error" if is_err else "deployment",
                    actor=self.config.agent_key,
                    metadata={"duration_seconds": ms / 1000.0},
                )
            case _:
                return None

    async def execute_stream(
        self,
        task_config: dict[str, Any],
        timeout: int = 30,
        org_id: str | None = None,
        org_name: str | None = None,
        github_token: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Execute command and yield events in real-time (NDJSON parsing)."""
        start_time = time()
        model = task_config.get("model", "gpt-5")
        logger.info(f"[AGENT STREAM] Starting streaming execution for {self.config.agent_key} (model={model})")

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

        logger.info(f"[AGENT STREAM CMD] {' '.join(cmd)} (model={model})")

        if org_id:
            task_title = task_config.get("prompt", "").split("\n")[0][:100]
            asyncio.create_task(
                create_event(
                    org_id=org_id,
                    type="message",
                    content=task_title or "Task started",
                    org_name=org_name,
                    actor=self.config.agent_key,
                )
            )

        subprocess_env = None
        if github_token:
            subprocess_env = {**os.environ, "GITHUB_TOKEN": github_token, "GH_TOKEN": github_token}
            logger.info(f"[AGENT STREAM] GitHub token injected for PR creation")

        logger.info(f"[AGENT STREAM] Spawning subprocess: {self.config.command}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=subprocess_env,
        )
        logger.info(f"[AGENT STREAM] Process started (pid={process.pid})")

        event_queue = asyncio.Queue()
        process_done = asyncio.Event()

        async def stream_stdout():
            """Parse NDJSON from stdout and queue events."""
            if process.stdout:
                async for line in process.stdout:
                    line_text = line.decode().rstrip()
                    if line_text:
                        try:
                            raw_event = json.loads(line_text)
                            parsed_event = parse_cursor_event(raw_event)
                            await event_queue.put(
                                {"type": "agent_event", "event": parsed_event, "timestamp": datetime.now().isoformat()}
                            )
                            if parsed_event.type == "thinking":
                                logger.debug(f"[AGENT STREAM EVENT] thinking")
                            else:
                                logger.info(f"[AGENT STREAM EVENT] {parsed_event.type}")
                        except json.JSONDecodeError:
                            await event_queue.put(
                                {"type": "agent_output", "content": line_text, "timestamp": datetime.now().isoformat()}
                            )
                            logger.info(f"[AGENT STREAM OUTPUT] {line_text[:100]}")

        async def stream_stderr():
            """Stream stderr as error events."""
            if process.stderr:
                async for line in process.stderr:
                    line_text = line.decode().rstrip()
                    if line_text:
                        await event_queue.put(
                            {"type": "agent_error", "content": line_text, "timestamp": datetime.now().isoformat()}
                        )
                        logger.warning(f"[AGENT STREAM ERROR] {line_text[:100]}")

        async def wait_for_process():
            """Wait for process completion and signal done."""
            await process.wait()
            process_done.set()

        tasks = [
            asyncio.create_task(stream_stdout()),
            asyncio.create_task(stream_stderr()),
            asyncio.create_task(wait_for_process()),
        ]

        thinking_buffer: list[str] = []
        thinking_start: float | None = None

        while True:
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                if process_done.is_set() and event_queue.empty():
                    break
                continue

            typed_event = event.get("event") if isinstance(event, dict) else None

            public_event = (
                {**event, "event": typed_event.model_dump(mode="json")}
                if isinstance(typed_event, (BaseCursorEvent, BaseResponseEvent))
                else event
            )
            yield public_event

            if org_id and typed_event:
                evt = self._event_to_event(typed_event, org_id, org_name, thinking_buffer, thinking_start)
                match evt:
                    case ("buffer_thinking", text):
                        thinking_buffer.append(text)
                        thinking_start = thinking_start or time()
                    case ("flush_thinking", full_text, duration):
                        logger.info(f"[AGENT STREAM] Thinking complete ({duration:.1f}s, {len(full_text)} chars)")
                        asyncio.create_task(
                            create_event(
                                org_id=org_id,
                                type="thinking",
                                content=full_text,
                                org_name=org_name,
                                actor=self.config.agent_key,
                                metadata={"duration_seconds": duration},
                            )
                        )
                        thinking_buffer.clear()
                        thinking_start = None
                    case Event() as e:
                        logger.info(f"[AGENT STREAM] Publishing event: {e.type}")
                        asyncio.create_task(
                            create_event(
                                org_id=e.org_id,
                                type=e.type,
                                content=e.content,
                                org_name=e.org_name,
                                actor=e.actor,
                                metadata=e.metadata,
                            )
                        )

        execution_time = time() - start_time
        exit_code = process.returncode if process.returncode is not None else -1
        yield {
            "type": "agent_complete",
            "exit_code": exit_code,
            "execution_time": execution_time,
            "model": model,
            "timestamp": datetime.now().isoformat(),
        }
        logger.info(f"[AGENT STREAM COMPLETE] {execution_time:.2f}s (model={model}, exit={exit_code})")

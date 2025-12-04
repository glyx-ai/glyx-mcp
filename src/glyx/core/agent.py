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
from supabase import create_client

from glyx.mcp.models.cursor import (
    BaseCursorEvent,
    CursorThinkingEvent,
    CursorToolCallEvent,
    parse_cursor_event,
)
from glyx.mcp.models.response import (
    BaseResponseEvent,
    parse_response_event,
    summarize_tool_activity,
)
from glyx.mcp.settings import settings
from glyx.mcp.websocket_manager import broadcast_event

logger = logging.getLogger(__name__)


class ActivityType(str, Enum):
    """Activity types for the activity feed."""
    MESSAGE = "message"
    CODE = "code"
    REVIEW = "review"
    DEPLOYMENT = "deployment"
    ERROR = "error"
    TOOL_CALL = "tool_call"
    THINKING = "thinking"


class ActivityActor(str, Enum):
    """Activity actor types."""
    AGENT = "agent"
    USER = "user"


class ActivityMetadata(BaseModel):
    """Structured metadata for activity records."""
    tool_name: str | None = None
    tool_args: dict[str, str] | None = None
    file_path: str | None = None
    duration_seconds: float | None = None
    exit_code: int | None = None
    full_text: str | None = None


class ActivityCreate(BaseModel):
    """Activity creation model for Supabase insert."""
    org_id: str
    org_name: str | None = None
    actor: ActivityActor = ActivityActor.AGENT
    type: ActivityType = ActivityType.MESSAGE
    role: str | None = None
    content: str
    metadata: ActivityMetadata | None = None


def get_supabase():
    """Get Supabase client for activity creation."""
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")
    return create_client(settings.supabase_url, settings.supabase_anon_key)


async def create_activity(activity: ActivityCreate) -> None:
    """Create an activity record in Supabase (non-blocking)."""
    client = get_supabase()
    client.table("activities").insert(activity.model_dump()).execute()
    logger.info(f"[ACTIVITY] Created: {activity.type.value} - {activity.content[:50]}")


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

    async def execute_stream(
        self,
        task_config: dict[str, Any],
        timeout: int = 30,
        org_id: str | None = None,
        org_name: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Execute command and yield events in real-time (NDJSON parsing).

        Args:
            task_config: Agent task configuration (prompt, model, etc.)
            timeout: Execution timeout in seconds
            org_id: Organization ID for activity creation
            org_name: Organization name for activity creation
        """
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

        # Create "started" activity
        if org_id:
            task_title = task_config.get("prompt", "").split("\n")[0][:100]
            asyncio.create_task(create_activity(ActivityCreate(
                org_id=org_id,
                org_name=org_name,
                content=task_title or "Task started",
                type=ActivityType.MESSAGE,
                role=self.config.agent_key,
            )))

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
                            raw_event = json.loads(line_text)
                            # Use typed cursor event parsing for cursor-agent
                            parsed_event = parse_cursor_event(raw_event)
                            await event_queue.put({
                                "type": "agent_event",
                                "event": parsed_event,
                                "timestamp": datetime.now().isoformat()
                            })
                            if parsed_event.type == "thinking":
                                logger.debug(f"[AGENT STREAM EVENT] thinking")
                            else:
                                logger.info(f"[AGENT STREAM EVENT] {parsed_event.type}")
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

        # Thinking aggregation state
        thinking_buffer: list[str] = []
        thinking_start: float | None = None

        try:
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                    typed_event = event.get("event") if isinstance(event, dict) else None

                    # Serialize Pydantic models for the public event
                    if isinstance(typed_event, (BaseCursorEvent, BaseResponseEvent)):
                        public_event = {**event, "event": typed_event.model_dump(mode="json")}
                    else:
                        public_event = event

                    yield public_event

                    # Create activity for tool call events using typed payloads
                    if org_id and isinstance(typed_event, CursorToolCallEvent):
                        tool_name = typed_event.get_tool_name()
                        preview = typed_event.get_preview()
                        file_path = typed_event.get_file_path() if hasattr(typed_event, 'get_file_path') else None
                        asyncio.create_task(create_activity(ActivityCreate(
                            org_id=org_id,
                            org_name=org_name,
                            content=tool_name,
                            type=ActivityType.TOOL_CALL,
                            role=self.config.agent_key,
                            metadata=ActivityMetadata(
                                tool_name=tool_name,
                                file_path=file_path or preview,
                            ),
                        )))
                    elif org_id and isinstance(typed_event, BaseResponseEvent):
                        # Fallback for non-cursor events
                        summary = summarize_tool_activity(typed_event)
                        if summary:
                            tool_name, args_preview = summary
                            asyncio.create_task(create_activity(ActivityCreate(
                                org_id=org_id,
                                org_name=org_name,
                                content=tool_name,
                                type=ActivityType.TOOL_CALL,
                                role=self.config.agent_key,
                                metadata=ActivityMetadata(
                                    tool_name=tool_name,
                                    file_path=args_preview,
                                ),
                            )))

                    # Aggregate thinking events into single activity
                    if org_id and isinstance(typed_event, CursorThinkingEvent):
                        if typed_event.subtype == "delta":
                            thinking_buffer.append(typed_event.text)
                            if thinking_start is None:
                                thinking_start = time()
                        elif typed_event.subtype == "completed":
                            if thinking_buffer:
                                duration = time() - thinking_start if thinking_start else 0
                                full_text = "".join(thinking_buffer)
                                asyncio.create_task(create_activity(ActivityCreate(
                                    org_id=org_id,
                                    org_name=org_name,
                                    content=full_text[:500],
                                    type=ActivityType.THINKING,
                                    role=self.config.agent_key,
                                    metadata=ActivityMetadata(
                                        duration_seconds=duration,
                                        full_text=full_text,
                                    ),
                                )))
                                thinking_buffer.clear()
                                thinking_start = None

                except asyncio.TimeoutError:
                    if process_done.is_set() and event_queue.empty():
                        break

            execution_time = time() - start_time
            exit_code = process.returncode if process.returncode is not None else -1
            yield {
                "type": "agent_complete",
                "exit_code": exit_code,
                "execution_time": execution_time,
                "timestamp": datetime.now().isoformat()
            }
            logger.info(f"[AGENT STREAM COMPLETE] {execution_time:.2f}s (exit={exit_code})")

            # Create completion activity
            if org_id:
                activity_type = ActivityType.DEPLOYMENT if exit_code == 0 else ActivityType.ERROR
                content = "Task completed" if exit_code == 0 else "Task failed"
                asyncio.create_task(create_activity(ActivityCreate(
                    org_id=org_id,
                    org_name=org_name,
                    content=content,
                    type=activity_type,
                    role=self.config.agent_key,
                    metadata=ActivityMetadata(
                        duration_seconds=execution_time,
                        exit_code=exit_code,
                    ),
                )))

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            yield {
                "type": "agent_timeout",
                "timeout": timeout,
                "timestamp": datetime.now().isoformat()
            }
            logger.error(f"[AGENT STREAM TIMEOUT] Killed after {timeout}s")

            # Create timeout activity
            if org_id:
                asyncio.create_task(create_activity(ActivityCreate(
                    org_id=org_id,
                    org_name=org_name,
                    content="Task timed out",
                    type=ActivityType.ERROR,
                    role=self.config.agent_key,
                    metadata=ActivityMetadata(
                        duration_seconds=float(timeout),
                    ),
                )))
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()

"""Typed representations of cursor-agent NDJSON event payloads."""

from __future__ import annotations

import json
from enum import Enum
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _truncate(text: str, limit: int = 50) -> str:
    return f"{text[:limit]}…" if len(text) > limit else text


# Base event types


class CursorEventType(str, Enum):
    SYSTEM = "system"
    USER = "user"
    THINKING = "thinking"
    ASSISTANT = "assistant"
    TOOL_CALL = "tool_call"
    RESULT = "result"


class BaseCursorEvent(BaseModel):
    type: str
    session_id: str | None = None

    model_config = ConfigDict(extra="ignore")


class CursorSystemEvent(BaseCursorEvent):
    type: Literal["system"] = "system"
    subtype: Literal["init"] = "init"
    cwd: str = ""
    model: str = ""
    api_key_source: str = Field("", alias="apiKeySource")
    permission_mode: str = Field("default", alias="permissionMode")

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class CursorUserEvent(BaseCursorEvent):
    type: Literal["user"] = "user"
    message: dict[str, Any] = Field(default_factory=dict)


class CursorThinkingEvent(BaseCursorEvent):
    type: Literal["thinking"] = "thinking"
    subtype: Literal["delta", "completed"] = "delta"
    text: str = ""
    timestamp_ms: int = 0


class CursorAssistantEvent(BaseCursorEvent):
    type: Literal["assistant"] = "assistant"
    message: dict[str, Any] = Field(default_factory=dict)
    model_call_id: str = ""
    timestamp_ms: int = 0


class CursorResultEvent(BaseCursorEvent):
    type: Literal["result"] = "result"
    subtype: Literal["success", "error"] = "success"
    result: str = ""
    is_error: bool = False
    duration_ms: int = 0
    duration_api_ms: int = 0
    request_id: str = ""


# Tool call protocol


class ToolCall(Protocol):
    """Protocol for tool call payloads. All implementations must provide these."""

    @property
    def tool_name(self) -> str: ...

    @property
    def preview(self) -> str: ...


# Tool call args - strict, no extras


class ShellToolCallArgs(BaseModel):
    command: str
    working_directory: str = Field("", alias="workingDirectory")
    timeout: int = 300000

    model_config = ConfigDict(populate_by_name=True)


class FileToolCallArgs(BaseModel):
    path: str


class McpToolCallArgs(BaseModel):
    """MCP tool args are dynamic - allow extras here."""

    model_config = ConfigDict(extra="allow")


# Tool result types


class ToolCallResult(BaseModel):
    """Generic tool call result."""

    model_config = ConfigDict(extra="allow")


# Tool call implementations


class ShellToolCall(BaseModel):
    args: ShellToolCallArgs | None = None
    result: ToolCallResult | None = None

    @model_validator(mode="after")
    def validate_has_args_or_result(self) -> "ShellToolCall":
        if self.args is None and self.result is None:
            raise ValueError("ShellToolCall must have args or result")
        return self

    @property
    def tool_name(self) -> str:
        if self.args:
            return f"shell: {_truncate(self.args.command)}"
        return "shell"

    @property
    def preview(self) -> str:
        return self.args.command if self.args else ""


class ReadToolCall(BaseModel):
    args: FileToolCallArgs | None = None
    result: ToolCallResult | None = None

    @model_validator(mode="after")
    def validate_has_args_or_result(self) -> "ReadToolCall":
        if self.args is None and self.result is None:
            raise ValueError("ReadToolCall must have args or result")
        return self

    @property
    def tool_name(self) -> str:
        return f"read: {self.args.path}" if self.args else "read_file"

    @property
    def preview(self) -> str:
        if self.args:
            return self.args.path
        if self.result:
            content = str(getattr(self.result, "content", ""))
            return _truncate(content, 100) if content else ""
        return ""


class WriteToolCall(BaseModel):
    args: FileToolCallArgs | None = None
    result: ToolCallResult | None = None

    @model_validator(mode="after")
    def validate_has_args_or_result(self) -> "WriteToolCall":
        if self.args is None and self.result is None:
            raise ValueError("WriteToolCall must have args or result")
        return self

    @property
    def tool_name(self) -> str:
        return f"write: {self.args.path}" if self.args else "write_file"

    @property
    def preview(self) -> str:
        return self.args.path if self.args else ""


class EditToolCall(BaseModel):
    args: FileToolCallArgs | None = None
    result: ToolCallResult | None = None

    @model_validator(mode="after")
    def validate_has_args_or_result(self) -> "EditToolCall":
        if self.args is None and self.result is None:
            raise ValueError("EditToolCall must have args or result")
        return self

    @property
    def tool_name(self) -> str:
        return f"edit: {self.args.path}" if self.args else "edit_file"

    @property
    def preview(self) -> str:
        return self.args.path if self.args else ""


class McpToolCall(BaseModel):
    server_label: str = Field("", alias="serverLabel")
    name: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    result: ToolCallResult | None = None

    model_config = ConfigDict(populate_by_name=True)

    @property
    def tool_name(self) -> str:
        if self.server_label and self.name:
            return f"{self.server_label}:{self.name}"
        return self.name or self.server_label or "mcp_tool"

    @property
    def preview(self) -> str:
        if not self.args:
            return ""
        try:
            return _truncate(json.dumps(self.args), 100)
        except (TypeError, ValueError):
            return ""


# Tool call payload container


class ToolCallPayload(BaseModel):
    """Container for cursor-agent tool calls. Exactly one tool type must be present."""

    shell_tool_call: ShellToolCall | None = Field(None, alias="shellToolCall")
    read_tool_call: ReadToolCall | None = Field(None, alias="readToolCall")
    write_tool_call: WriteToolCall | None = Field(None, alias="writeToolCall")
    edit_tool_call: EditToolCall | None = Field(None, alias="editToolCall")
    mcp_tool_call: McpToolCall | None = Field(None, alias="mcpToolCall")

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @property
    def active_tool(self) -> ToolCall:
        """Get the active tool call. Raises if none found."""
        tools: tuple[ToolCall | None, ...] = (
            self.shell_tool_call,
            self.read_tool_call,
            self.write_tool_call,
            self.edit_tool_call,
            self.mcp_tool_call,
        )
        tool = next((t for t in tools if t is not None), None)
        if tool is None:
            raise ValueError("ToolCallPayload has no active tool")
        return tool

    @property
    def tool_name(self) -> str:
        try:
            return self.active_tool.tool_name
        except ValueError:
            return "tool_call"

    @property
    def preview(self) -> str:
        try:
            return self.active_tool.preview
        except ValueError:
            return ""


# Tool call event


class CursorToolCallEvent(BaseCursorEvent):
    type: Literal["tool_call"] = "tool_call"
    subtype: Literal["started", "completed"] = "started"
    call_id: str = ""
    tool_call: ToolCallPayload
    model_call_id: str = ""
    timestamp_ms: int = 0

    @property
    def tool_name(self) -> str:
        return self.tool_call.tool_name

    @property
    def preview(self) -> str:
        return self.tool_call.preview

    # Keep old method names for compatibility
    def get_tool_name(self) -> str:
        return self.tool_name

    def get_preview(self) -> str:
        return self.preview


# Event parsing


CursorEvent = Annotated[
    CursorSystemEvent
    | CursorUserEvent
    | CursorThinkingEvent
    | CursorAssistantEvent
    | CursorToolCallEvent
    | CursorResultEvent,
    Field(discriminator="type"),
]


CURSOR_EVENT_MAP: dict[str, type[BaseCursorEvent]] = {
    "system": CursorSystemEvent,
    "user": CursorUserEvent,
    "thinking": CursorThinkingEvent,
    "assistant": CursorAssistantEvent,
    "tool_call": CursorToolCallEvent,
    "result": CursorResultEvent,
}


def parse_cursor_event(payload: dict[str, Any]) -> BaseCursorEvent:
    """Parse a cursor-agent NDJSON event into a typed model."""
    event_type = payload.get("type", "")
    model = CURSOR_EVENT_MAP.get(event_type, BaseCursorEvent)
    return model.model_validate(payload)

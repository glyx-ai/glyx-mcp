"""Typed representations of Vercel AI SDK ResponseEvent payloads."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from glyx_sdk.models.cursor import CursorToolCallEvent


class ResponseEventType(str, Enum):
    """Supported response event types."""

    RESPONSE_CREATED = "response.created"
    RESPONSE_COMPLETED = "response.completed"
    RESPONSE_INCOMPLETE = "response.incomplete"
    OUTPUT_ITEM_ADDED = "response.output_item.added"
    OUTPUT_ITEM_DONE = "response.output_item.done"
    OUTPUT_TEXT_DELTA = "response.output_text.delta"
    OUTPUT_TEXT_ANNOTATION_ADDED = "response.output_text.annotation.added"
    FUNCTION_CALL_ARGS_DELTA = "response.function_call_arguments.delta"
    IMAGE_GENERATION_PARTIAL = "response.image_generation_call.partial_image"
    CODE_INTERPRETER_CODE_DELTA = "response.code_interpreter_call_code.delta"
    CODE_INTERPRETER_CODE_DONE = "response.code_interpreter_call_code.done"
    REASONING_SUMMARY_PART_ADDED = "response.reasoning_summary_part.added"
    REASONING_SUMMARY_PART_DONE = "response.reasoning_summary_part.done"
    REASONING_SUMMARY_TEXT_DELTA = "response.reasoning_summary_text.delta"
    ERROR = "error"
    UNKNOWN = "unknown_chunk"


class StreamEventType(str, Enum):
    """Envelope types emitted by streaming endpoints."""

    PROGRESS = "progress"
    AGENT_EVENT = "agent_event"
    AGENT_OUTPUT = "agent_output"
    AGENT_ERROR = "agent_error"
    AGENT_COMPLETE = "agent_complete"
    AGENT_TIMEOUT = "agent_timeout"
    ERROR = "error"


class ResponseUsageDetails(BaseModel):
    """Fine-grained token accounting."""

    cached_tokens: int | None = None
    reasoning_tokens: int | None = None


class ResponseUsage(BaseModel):
    """Token usage metadata returned with completion events."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    input_tokens_details: ResponseUsageDetails | None = None
    output_tokens_details: ResponseUsageDetails | None = None


class ResponseMetadata(BaseModel):
    """Basic response metadata shared by multiple events."""

    id: str | None = None
    created_at: int | None = None
    model: str | None = None
    service_tier: str | None = None


class ResponseCompletionPayload(ResponseMetadata):
    """Completion payload containing usage details."""

    usage: ResponseUsage | None = None
    incomplete_details: dict[str, Any] | None = None


class ResponseError(BaseModel):
    """Error payload emitted by the Responses stream."""

    type: str
    code: str | None = None
    message: str
    param: str | None = None


class BaseResponseEvent(BaseModel):
    """Base class for all typed response events."""

    type: str

    model_config = ConfigDict(extra="allow")


class ResponseCreatedEvent(BaseResponseEvent):
    """`response.created` event."""

    type: str = ResponseEventType.RESPONSE_CREATED.value
    response: ResponseMetadata


class ResponseCompletedEvent(BaseResponseEvent):
    """`response.completed` event."""

    type: str = ResponseEventType.RESPONSE_COMPLETED.value
    response: ResponseCompletionPayload


class ResponseIncompleteEvent(BaseResponseEvent):
    """`response.incomplete` event."""

    type: str = ResponseEventType.RESPONSE_INCOMPLETE.value
    response: ResponseCompletionPayload


class ResponseOutputTextDeltaEvent(BaseResponseEvent):
    """`response.output_text.delta` event."""

    type: str = ResponseEventType.OUTPUT_TEXT_DELTA.value
    item_id: str
    delta: str
    logprobs: list[dict[str, Any]] | None = None


class ResponseFunctionCallArgumentsDeltaEvent(BaseResponseEvent):
    """`response.function_call_arguments.delta` event."""

    type: str = ResponseEventType.FUNCTION_CALL_ARGS_DELTA.value
    item_id: str
    output_index: int
    delta: str


class ResponseOutputItemAddedEvent(BaseResponseEvent):
    """`response.output_item.added` event."""

    type: str = ResponseEventType.OUTPUT_ITEM_ADDED.value
    output_index: int
    item: dict[str, Any]


class ResponseOutputItemDoneEvent(BaseResponseEvent):
    """`response.output_item.done` event."""

    type: str = ResponseEventType.OUTPUT_ITEM_DONE.value
    output_index: int
    item: dict[str, Any]


class ResponseOutputTextAnnotationAddedEvent(BaseResponseEvent):
    """`response.output_text.annotation.added` event."""

    type: str = ResponseEventType.OUTPUT_TEXT_ANNOTATION_ADDED.value
    annotation: dict[str, Any]


class ResponseReasoningSummaryPartAddedEvent(BaseResponseEvent):
    """`response.reasoning_summary_part.added` event."""

    type: str = ResponseEventType.REASONING_SUMMARY_PART_ADDED.value
    item_id: str
    summary_index: int


class ResponseReasoningSummaryPartDoneEvent(BaseResponseEvent):
    """`response.reasoning_summary_part.done` event."""

    type: str = ResponseEventType.REASONING_SUMMARY_PART_DONE.value
    item_id: str
    summary_index: int


class ResponseReasoningSummaryTextDeltaEvent(BaseResponseEvent):
    """`response.reasoning_summary_text.delta` event."""

    type: str = ResponseEventType.REASONING_SUMMARY_TEXT_DELTA.value
    item_id: str
    summary_index: int
    delta: str


class ResponseImageGenerationPartialEvent(BaseResponseEvent):
    """`response.image_generation_call.partial_image` event."""

    type: str = ResponseEventType.IMAGE_GENERATION_PARTIAL.value
    item_id: str
    output_index: int
    partial_image_b64: str


class ResponseCodeInterpreterDeltaEvent(BaseResponseEvent):
    """`response.code_interpreter_call_code.delta` event."""

    type: str = ResponseEventType.CODE_INTERPRETER_CODE_DELTA.value
    item_id: str
    output_index: int
    delta: str


class ResponseCodeInterpreterDoneEvent(BaseResponseEvent):
    """`response.code_interpreter_call_code.done` event."""

    type: str = ResponseEventType.CODE_INTERPRETER_CODE_DONE.value
    item_id: str
    output_index: int
    code: str


class ResponseErrorEvent(BaseResponseEvent):
    """`error` event."""

    type: str = ResponseEventType.ERROR.value
    error: ResponseError


class UnknownResponseEvent(BaseResponseEvent):
    """Fallback for unknown event types."""

    raw: dict[str, Any]


class ResponseFunctionCall(BaseModel):
    """Typed view over a `function_call` response item."""

    type: str = "function_call"
    id: str | None = None
    call_id: str
    name: str
    arguments: str
    status: str | None = None

    model_config = ConfigDict(extra="allow")


EVENT_MODEL_MAP: dict[str, type[BaseResponseEvent]] = {
    ResponseEventType.RESPONSE_CREATED.value: ResponseCreatedEvent,
    ResponseEventType.RESPONSE_COMPLETED.value: ResponseCompletedEvent,
    ResponseEventType.RESPONSE_INCOMPLETE.value: ResponseIncompleteEvent,
    ResponseEventType.OUTPUT_ITEM_ADDED.value: ResponseOutputItemAddedEvent,
    ResponseEventType.OUTPUT_ITEM_DONE.value: ResponseOutputItemDoneEvent,
    ResponseEventType.OUTPUT_TEXT_DELTA.value: ResponseOutputTextDeltaEvent,
    ResponseEventType.OUTPUT_TEXT_ANNOTATION_ADDED.value: (ResponseOutputTextAnnotationAddedEvent),
    ResponseEventType.FUNCTION_CALL_ARGS_DELTA.value: (ResponseFunctionCallArgumentsDeltaEvent),
    ResponseEventType.IMAGE_GENERATION_PARTIAL.value: (ResponseImageGenerationPartialEvent),
    ResponseEventType.CODE_INTERPRETER_CODE_DELTA.value: (ResponseCodeInterpreterDeltaEvent),
    ResponseEventType.CODE_INTERPRETER_CODE_DONE.value: (ResponseCodeInterpreterDoneEvent),
    ResponseEventType.REASONING_SUMMARY_PART_ADDED.value: (ResponseReasoningSummaryPartAddedEvent),
    ResponseEventType.REASONING_SUMMARY_PART_DONE.value: (ResponseReasoningSummaryPartDoneEvent),
    ResponseEventType.REASONING_SUMMARY_TEXT_DELTA.value: (ResponseReasoningSummaryTextDeltaEvent),
    ResponseEventType.ERROR.value: ResponseErrorEvent,
}


def parse_response_event(payload: Mapping[str, Any]) -> BaseResponseEvent:
    """Parse a raw JSON payload into a typed response event."""
    event_type = payload.get("type")
    event_type_str = event_type if isinstance(event_type, str) else ""
    model = EVENT_MODEL_MAP.get(event_type_str, UnknownResponseEvent)
    try:
        return model.model_validate(payload)
    except ValidationError:
        return UnknownResponseEvent(
            type=event_type or ResponseEventType.UNKNOWN.value,
            raw=dict(payload),
        )


def parse_function_call_item(
    item: Mapping[str, Any],
) -> ResponseFunctionCall | None:
    """Parse a response item into a typed function call representation."""
    if item.get("type") != "function_call":
        return None
    try:
        return ResponseFunctionCall.model_validate(item)
    except ValidationError:
        return None


def extract_function_call(
    event: BaseResponseEvent,
) -> ResponseFunctionCall | None:
    """Extract a typed function call from output item events."""
    if isinstance(
        event,
        (ResponseOutputItemAddedEvent, ResponseOutputItemDoneEvent),
    ):
        return parse_function_call_item(event.item)
    return None


def _truncate_preview(value: str, limit: int = 80) -> str:
    return value if len(value) <= limit else f"{value[:limit]}…"


def _preview_mapping(data: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for idx, (key, val) in enumerate(data.items()):
        if idx >= 3:
            break
        parts.append(f"{key}={_preview_value(val) or ''}")
    return _truncate_preview(", ".join(parts))


def _preview_sequence(data: Sequence[Any]) -> str:
    preview_items = (_preview_value(item) or "" for item in data[:3])
    parts = ", ".join(preview_items)
    return _truncate_preview(parts)


def _preview_value(value: Any) -> str | None:
    match value:
        case None:
            return None
        case str() as text:
            stripped = text.strip()
            if not stripped:
                return None
            try:
                parsed = json.loads(stripped)
                return _preview_value(parsed)
            except Exception:
                return _truncate_preview(stripped)
        case Mapping() as mapping:
            return _preview_mapping(mapping)
        case Sequence() as seq:
            return _preview_sequence(seq)
        case _:
            return _truncate_preview(str(value))


def _extract_cursor_tool_name(item: Mapping[str, Any]) -> str | None:
    """Extract tool name from cursor-agent tool_call events."""
    tool_call = item.get("tool_call")
    if not isinstance(tool_call, Mapping):
        return None

    for tool_type, tool_data in tool_call.items():
        if not isinstance(tool_data, Mapping):
            continue

        if tool_type == "mcpToolCall":
            server = tool_data.get("serverLabel", "")
            name = tool_data.get("name", "")
            if server and name:
                return f"{server}:{name}"
            return name or server or "mcp_tool"

        if tool_type == "shellToolCall":
            args = tool_data.get("args", {})
            command = args.get("command", "") if isinstance(args, Mapping) else ""
            if command:
                short_cmd = command[:50] + "…" if len(command) > 50 else command
                return f"shell: {short_cmd}"
            return "shell"

        if tool_type == "readToolCall":
            args = tool_data.get("args", {})
            path = args.get("path", "") if isinstance(args, Mapping) else ""
            if path:
                return f"read: {path}"
            return "read_file"

        if tool_type == "writeToolCall":
            args = tool_data.get("args", {})
            path = args.get("path", "") if isinstance(args, Mapping) else ""
            if path:
                return f"write: {path}"
            return "write_file"

        if tool_type == "editToolCall":
            args = tool_data.get("args", {})
            path = args.get("path", "") if isinstance(args, Mapping) else ""
            if path:
                return f"edit: {path}"
            return "edit_file"

        import re

        readable = re.sub(r"ToolCall$", "", tool_type)
        readable = re.sub(r"([a-z])([A-Z])", r"\1_\2", readable).lower()
        return readable or tool_type

    return None


def _extract_tool_name(item: Mapping[str, Any]) -> str:
    cursor_name = _extract_cursor_tool_name(item)
    if cursor_name:
        return cursor_name

    candidates = (
        item.get("name"),
        item.get("tool_name"),
        item.get("server_label"),
        item.get("id"),
        item.get("type"),
    )
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate
    return "tool_call"


def _extract_tool_payload(item: Mapping[str, Any]) -> Any:
    payload_keys = (
        "output",
        "result",
        "response",
        "content",
        "arguments",
        "args",
        "action",
        "operation",
        "message",
        "text",
    )
    for key in payload_keys:
        if key in item:
            return item[key]
    return item


def _summarize_mapping(item: Mapping[str, Any]) -> tuple[str, str | None]:
    tool_name = _extract_tool_name(item)
    payload = _preview_value(_extract_tool_payload(item))
    return tool_name, payload


def summarize_tool_activity(
    event: BaseResponseEvent | CursorToolCallEvent,
) -> tuple[str, str | None] | None:
    """Produce a human-friendly summary for tool-related response events."""
    if isinstance(event, CursorToolCallEvent):
        return (event.get_tool_name(), event.get_preview())

    match event:
        case ResponseOutputItemAddedEvent(item=item):
            if isinstance(item, Mapping):
                return _summarize_mapping(item)
        case ResponseOutputItemDoneEvent(item=item):
            if isinstance(item, Mapping):
                return _summarize_mapping(item)
        case ResponseFunctionCallArgumentsDeltaEvent(
            delta=delta,
            item_id=item_id,
        ):
            name = f"{item_id or 'function_call'}:args"
            return (name, _preview_value(delta))
        case UnknownResponseEvent(raw=raw, type=event_type):
            if isinstance(raw, Mapping) and event_type in {
                "tool_call",
                "tool_result",
                "tool_output",
                "function_call",
            }:
                return _summarize_mapping(raw)
        case _:
            return None
    return None


from glyx.mcp.models.cursor import (
    CursorToolCallEvent,
    FileToolCallArgs,
    McpToolCall,
    ReadToolCall,
    ShellToolCall,
    ShellToolCallArgs,
    ToolCallPayload,
)
from glyx.mcp.models.response import (
    ResponseEventType,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputTextDeltaEvent,
    UnknownResponseEvent,
    extract_function_call,
    parse_response_event,
    summarize_tool_activity,
)


def test_parse_response_event_returns_typed_delta() -> None:
    payload = {
        "type": ResponseEventType.OUTPUT_TEXT_DELTA.value,
        "item_id": "msg_123",
        "delta": "Hello",
        "logprobs": None,
    }

    event = parse_response_event(payload)

    assert isinstance(event, ResponseOutputTextDeltaEvent)
    assert event.delta == "Hello"
    assert event.item_id == "msg_123"


def test_extract_function_call_from_output_item() -> None:
    payload = {
        "type": ResponseEventType.OUTPUT_ITEM_ADDED.value,
        "output_index": 0,
        "item": {
            "type": "function_call",
            "id": "fn_1",
            "call_id": "call_1",
            "name": "getWeather",
            "arguments": '{"city":"Paris"}',
        },
    }

    event = parse_response_event(payload)

    assert isinstance(event, ResponseOutputItemAddedEvent)
    function_call = extract_function_call(event)
    assert function_call is not None
    assert function_call.name == "getWeather"
    assert function_call.arguments == '{"city":"Paris"}'


def test_unknown_response_event_falls_back_to_raw() -> None:
    payload = {"type": "custom.event", "foo": "bar"}

    event = parse_response_event(payload)

    assert isinstance(event, UnknownResponseEvent)
    assert event.raw == payload


def test_summarize_tool_activity_handles_function_call() -> None:
    event = ResponseOutputItemAddedEvent(
        type=ResponseEventType.OUTPUT_ITEM_ADDED.value,
        output_index=0,
        item={
            "type": "function_call",
            "name": "getWeather",
            "arguments": '{"city": "Berlin", "units": "metric"}',
        },
    )

    summary = summarize_tool_activity(event)

    assert summary is not None
    tool_name, preview = summary
    assert tool_name == "getWeather"
    assert preview and "Berlin" in preview


def test_summarize_tool_activity_handles_shell_output() -> None:
    event = ResponseOutputItemDoneEvent(
        type=ResponseEventType.OUTPUT_ITEM_DONE.value,
        output_index=1,
        item={
            "type": "shell_call",
            "call_id": "shell_123",
            "status": "completed",
            "output": [{"stdout": "done", "stderr": "", "outcome": {"type": "exit", "exit_code": 0}}],
        },
    )

    summary = summarize_tool_activity(event)

    assert summary is not None
    tool_name, preview = summary
    # Tool type "shell_call" is more descriptive than call_id "shell_123"
    assert tool_name == "shell_call"
    assert preview and "done" in preview


def test_summarize_tool_activity_handles_unknown_tool_call() -> None:
    event = UnknownResponseEvent(
        type="tool_call",
        raw={
            "type": "tool_call",
            "name": "search_docs",
            "arguments": {"query": "cursor streaming"},
        },
    )

    summary = summarize_tool_activity(event)

    assert summary is not None
    tool_name, preview = summary
    assert tool_name == "search_docs"
    assert preview and "cursor streaming" in preview


def test_summarize_tool_activity_handles_cursor_shell_tool() -> None:
    """Test cursor-agent shellToolCall event with typed models."""
    event = CursorToolCallEvent(
        type="tool_call",
        subtype="started",
        call_id="tool_abc123-xyz",
        tool_call=ToolCallPayload(
            shell_tool_call=ShellToolCall(
                args=ShellToolCallArgs(command="ls -la", working_directory="/home")
            )
        ),
    )

    summary = summarize_tool_activity(event)

    assert summary is not None
    tool_name, preview = summary
    assert tool_name == "shell: ls -la"
    assert preview == "ls -la"


def test_summarize_tool_activity_handles_cursor_read_tool() -> None:
    """Test cursor-agent readToolCall event with typed models."""
    event = CursorToolCallEvent(
        type="tool_call",
        subtype="started",
        call_id="tool_abc123-xyz",
        tool_call=ToolCallPayload(
            read_tool_call=ReadToolCall(args=FileToolCallArgs(path="pyproject.toml"))
        ),
    )

    summary = summarize_tool_activity(event)

    assert summary is not None
    tool_name, preview = summary
    assert tool_name == "read: pyproject.toml"
    assert preview == "pyproject.toml"


def test_summarize_tool_activity_handles_cursor_mcp_tool() -> None:
    """Test cursor-agent mcpToolCall event with typed models."""
    event = CursorToolCallEvent(
        type="tool_call",
        subtype="started",
        call_id="tool_abc123-xyz",
        tool_call=ToolCallPayload(
            mcp_tool_call=McpToolCall(
                server_label="supabase",
                name="execute_sql",
                args={"query": "SELECT 1"},
            )
        ),
    )

    summary = summarize_tool_activity(event)

    assert summary is not None
    tool_name, preview = summary
    assert tool_name == "supabase:execute_sql"
    assert preview is not None
    assert "SELECT 1" in preview


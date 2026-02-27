"""Streaming API routes (SSE and WebSocket)."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter, WebSocket
from fastapi.responses import StreamingResponse

from agents.items import ItemHelpers, MessageOutputItem, ReasoningItem, ToolCallItem, ToolCallOutputItem
from glyx_python_sdk import GlyxOrchestrator, build_task_prompt
from glyx_python_sdk.composable_agents import create_event
from glyx_python_sdk.types import StreamCursorRequest
from glyx_python_sdk.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Streaming"])


@router.post(
    "/stream/cursor",
    summary="Stream Orchestrator Execution",
    response_description="Server-Sent Events (SSE) stream of execution progress",
)
async def stream_cursor(body: StreamCursorRequest) -> StreamingResponse:
    """
    Stream real-time orchestrator execution using Server-Sent Events (SSE).

    The orchestrator coordinates multiple AI agents to complete complex tasks.
    This endpoint streams progress updates as the task executes.

    **Event Types:**
    - `progress`: Status updates (e.g., "Starting orchestrator...")
    - `tool_call`: When an agent tool is invoked
    - `tool_output`: Tool execution results
    - `message`: LLM responses
    - `thinking`: Internal reasoning steps
    - `complete`: Task completion
    - `error`: Error occurred

    **Request Body:**
    - `task`: Task object with id, title, description
    - `orchestration_id`: Orchestration UUID

    **Example Event:**
    ```
    data: {"type": "message", "content": "Implementing authentication...", "timestamp": "2025-12-04T13:45:00.000Z"}
    ```

    **Usage:**
    ```javascript
    const eventSource = new EventSource('/stream/cursor', {
        method: 'POST',
        body: JSON.stringify({task: {...}, orchestration_id: '...'})
    });
    eventSource.onmessage = (e) => {
        const data = JSON.parse(e.data);
        console.log(data.type, data.content);
    };
    ```
    """

    async def publish(event_type: str, content: str, metadata: dict | None = None):
        """Publish event to Supabase."""
        await create_event(
            orchestration_id=body.orchestration_id,
            type=event_type,
            content=content,
            metadata=metadata,
        )

    async def generate():
        try:
            prompt = build_task_prompt(body.task)
            logger.info(f"[STREAM] Executing task {body.task.id}: {body.task.title}")

            progress_data = {
                "type": "progress",
                "message": "🚀 Starting orchestrator...",
                "timestamp": datetime.now().isoformat(),
            }
            yield f"data: {json.dumps(progress_data)}\n\n"

            orchestrator = GlyxOrchestrator(
                agent_name="TaskOrchestrator",
                model="openrouter/anthropic/claude-sonnet-4",
                mcp_servers=[],
                session_id=f"task-{body.task.id}",
            )

            async for item in orchestrator.run_prompt_streamed_items(prompt):
                timestamp = datetime.now().isoformat()

                match item:
                    case ToolCallItem() as item:
                        tool_name = item.raw_item.name
                        await publish("tool_call", f"Tool: {tool_name}", {"tool_name": tool_name})
                        tool_data = {"type": "tool_call", "tool": tool_name, "timestamp": timestamp}
                        yield f"data: {json.dumps(tool_data)}\n\n"

                    case ToolCallOutputItem() as item:
                        output_data = {"type": "tool_output", "output": str(item.output)[:500], "timestamp": timestamp}
                        yield f"data: {json.dumps(output_data)}\n\n"

                    case MessageOutputItem() as item:
                        text = ItemHelpers.text_message_output(item)
                        await publish("message", text)
                        msg_data = {"type": "message", "content": text, "timestamp": timestamp}
                        yield f"data: {json.dumps(msg_data)}\n\n"

                    case ReasoningItem() as item:
                        await publish("thinking", str(item.raw_item)[:500])
                        think_data = {"type": "thinking", "content": str(item.raw_item), "timestamp": timestamp}
                        yield f"data: {json.dumps(think_data)}\n\n"

            await publish("complete", "Task completed")
            complete_data = {"type": "complete", "output": "Task completed", "timestamp": datetime.now().isoformat()}
            yield f"data: {json.dumps(complete_data)}\n\n"

            await orchestrator.cleanup()

        except Exception as e:
            logger.exception("Stream cursor error")
            await publish("error", str(e))
            yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'timestamp': datetime.now().isoformat()})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        await ws_manager.disconnect(websocket)

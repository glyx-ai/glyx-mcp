"""FastMCP server for coding agents with Aider integration."""

from __future__ import annotations

import logging
import sys

from fastmcp import FastMCP, Context
from fastmcp.utilities.logging import get_logger
from langfuse import Langfuse

from pathlib import Path
import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn
from datetime import datetime
import json

from glyx.mcp.realtime import manager as ws_manager
from glyx.core.agent import ComposableAgent, AgentKey

from glyx.core.registry import discover_and_register_agents
from glyx.mcp.orchestration.orchestrator import Orchestrator
from glyx.mcp.settings import settings
from glyx.mcp.tools.interact_with_user import ask_user
from glyx.mcp.tools.use_memory import (
    save_memory,
    search_memory,
)
from glyx.mcp.tools.session_tools import (
    list_sessions,
    get_session_messages,
)
from glyx.tasks.server import mcp as tasks_mcp
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
    ],
    force=True,
)

logger = logging.getLogger(__name__)


# Optional Langfuse instrumentation (only if keys are configured)
langfuse = None
if settings.langfuse_public_key and settings.langfuse_secret_key:
    langfuse = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    if not langfuse.auth_check():
        logger.warning(
            "Langfuse authentication failed. Tracing will be disabled. "
            "Check LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_HOST in your .env file."
        )
        langfuse = None
    else:
        logger.info("Langfuse instrumented. Preparing OpenAI agent instrumentation...")
        OpenAIAgentsInstrumentor().instrument()
else:
    logger.info("Langfuse not configured. Tracing disabled.")



# Configure FastMCP client logging (messages sent to MCP clients)
to_client_logger = get_logger(name="fastmcp.server.context.to_client")
to_client_logger.setLevel(level=logging.DEBUG)


mcp = FastMCP("glyx-mcp")

# Register tools with MCP server
logger.info("Initializing MCP tools...")

# Auto-discover and register agents from JSON configs
agents_dir = Path(__file__).parent.parent.parent.parent / "agents"
discover_and_register_agents(mcp, agents_dir)

# Register non-agent tools manually
mcp.tool(ask_user)
mcp.tool(search_memory)
mcp.tool(save_memory)
mcp.tool(list_sessions)
mcp.tool(get_session_messages)

# Mount task tracking server
logger.info("Mounting task tracking server...")
mcp.mount(tasks_mcp)



# Register orchestrator as a tool (not prompt) due to Claude Code bug with MCP prompts
# See: https://github.com/anthropics/claude-code/issues/6657
@mcp.tool
async def orchestrate(
    task: str,
    ctx: Context,
) -> str:
    """
    Orchestrate complex tasks by coordinating multiple AI agents with deep reasoning and stuff.

    Args:
        task: The task description to orchestrate across multiple agents
    """
    logger.info(f"orchestrate tool received - task: {task!r}")
    orchestrator = Orchestrator(ctx=ctx, model="gpt-5")

    # Run orchestration synchronously and return the result
    # (The orchestrator internally runs agents in parallel via OpenAI Agents SDK)
    try:
        result = await orchestrator.orchestrate(task)
        return f"✅ Orchestration completed successfully\n\n{result.output}"
    except Exception as e:
        logger.error(f"Orchestration failed: {e}")
        return f"❌ Orchestration failed: {e}"


def main() -> None:
    """Run the FastMCP server (stdio mode for Claude Code)."""
    mcp.run()


class StreamCursorRequest(BaseModel):
    """Request model for streaming cursor agent."""
    prompt: str
    model: str = "gpt-5"
    conversation_id: str | None = None


async def _run_ws_server(host: str = "0.0.0.0", port: int = 8001) -> None:
    """Run a lightweight FastAPI app for WebSocket realtime events."""

    app = FastAPI()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/stream/cursor")
    async def stream_cursor(body: StreamCursorRequest) -> StreamingResponse:
        """Stream cursor agent output with real-time NDJSON events."""

        async def generate():
            try:
                prompt = body.prompt
                model = body.model
                conversation_id = body.conversation_id

                yield f"data: {json.dumps({'type': 'progress', 'message': '🚀 Starting cursor agent...', 'timestamp': datetime.now().isoformat()})}\n\n"

                agent = ComposableAgent.from_key(AgentKey.CURSOR)

                # Stream events in real-time
                async for event in agent.execute_stream({
                    "prompt": prompt,
                    "model": model,
                    "force": True,
                    "output_format": "stream-json",
                }, timeout=600):
                    yield f"data: {json.dumps(event)}\n\n"

            except Exception as e:
                logger.exception("Stream cursor error")
                yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'timestamp': datetime.now().isoformat()})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await ws_manager.connect(websocket)
        try:
            # Consume incoming messages to keep the connection alive; ignore content.
            while True:
                await websocket.receive_text()
        except Exception:
            # Normal disconnect / network error
            pass
        finally:
            await ws_manager.disconnect(websocket)

    config = uvicorn.Config(app=app, host=host, port=port, log_level="info", loop="asyncio")
    server = uvicorn.Server(config)
    logger.info(f"Starting WebSocket server on ws://{host}:{port}/ws")
    await server.serve()


async def main_http() -> None:
    """Run HTTP MCP server and a companion WebSocket server for realtime events."""
    await asyncio.gather(
        mcp.run_http_async(
            transport="streamable-http",
            host="0.0.0.0",
            port=8000,
        ),
        _run_ws_server(host="0.0.0.0", port=8001),
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        import asyncio
        asyncio.run(main_http())
    else:
        main()

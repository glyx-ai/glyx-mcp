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
from fastapi.middleware.cors import CORSMiddleware
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
from glyx.mcp.tools.agent_crud import (
    create_agent,
    list_agents,
    delete_agent,
    get_agent,
)
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

# Agent CRUD tools (Supabase-backed)
mcp.tool(create_agent)
mcp.tool(list_agents)
mcp.tool(delete_agent)
mcp.tool(get_agent)


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


import os

# Create FastAPI app for additional routes (WebSocket, streaming, health)
api_app = FastAPI()

api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@api_app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@api_app.post("/stream/cursor")
async def stream_cursor(body: StreamCursorRequest) -> StreamingResponse:
    """Stream cursor agent output with real-time NDJSON events."""

    async def generate():
        try:
            prompt = body.prompt
            model = body.model

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


@api_app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        await ws_manager.disconnect(websocket)


# Feature Pipeline API
from glyx.core.pipelines import (
    Feature,
    FeatureCreate,
    FeatureUpdate,
    Pipeline,
    get_feature,
    list_features,
    save_feature,
    delete_feature,
)
from fastapi import HTTPException


@api_app.get("/features")
async def api_list_features(status: str | None = None) -> list[Feature]:
    """List all features."""
    return list_features(status)


@api_app.post("/features")
async def api_create_feature(body: FeatureCreate) -> Feature:
    """Create a new feature with default pipeline stages."""
    pipeline = Pipeline.create(body)
    return save_feature(pipeline.feature)


@api_app.get("/features/{feature_id}")
async def api_get_feature(feature_id: str) -> Feature:
    """Get a feature by ID."""
    feature = get_feature(feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")
    return feature


@api_app.patch("/features/{feature_id}")
async def api_update_feature(feature_id: str, body: FeatureUpdate) -> Feature:
    """Update a feature."""
    feature = get_feature(feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")
    updated = feature.model_copy(update=body.model_dump(exclude_unset=True))
    return save_feature(updated)


@api_app.delete("/features/{feature_id}")
async def api_delete_feature(feature_id: str) -> dict[str, str]:
    """Delete a feature."""
    if not delete_feature(feature_id):
        raise HTTPException(status_code=404, detail="Feature not found")
    return {"status": "deleted"}


# Agent API
class AgentResponse(BaseModel):
    """Response model for agent info."""
    name: str
    model: str
    description: str
    capabilities: list[str]
    status: str


@api_app.get("/agents")
async def api_list_agents() -> list[AgentResponse]:
    """List all available agents from JSON configs."""
    agents_path = Path(__file__).parent.parent.parent.parent / "agents"
    result: list[AgentResponse] = []

    for json_file in agents_path.glob("*.json"):
        try:
            agent = ComposableAgent.from_file(json_file)
            config = agent.config
            model_arg = config.args.get("model")
            model_default = model_arg.default if model_arg and model_arg.default else "gpt-5"
            result.append(AgentResponse(
                name=config.agent_key,
                model=str(model_default),
                description=config.description or f"Execute {config.agent_key} agent",
                capabilities=config.capabilities,
                status="online",
            ))
        except Exception as e:
            logger.warning(f"Failed to load agent from {json_file}: {e}")
            continue

    return result


from starlette.applications import Starlette
from starlette.routing import Mount


async def main_http() -> None:
    """Run HTTP MCP server with combined API routes (Cloud Run/Fly.io compatible)."""
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting combined MCP + API server on http://0.0.0.0:{port}")

    # Get the MCP HTTP app (using deprecated method for now - will update to http_app() later)
    mcp_app = mcp.streamable_http_app()

    # Create combined Starlette app that mounts both MCP and our custom API
    app = Starlette(
        routes=[
            Mount("/api", app=api_app),  # Our custom routes at /api/*
            Mount("/", app=mcp_app),     # MCP routes at root
        ]
    )

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        asyncio.run(main_http())
    else:
        main()

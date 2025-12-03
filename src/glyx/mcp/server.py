"""FastMCP server for coding agents with Aider integration."""

from __future__ import annotations

import logging
import sys

from fastmcp import FastMCP, Context
from fastmcp.utilities.logging import get_logger
from langfuse import Langfuse

from pathlib import Path
import asyncio
import os
import json
from datetime import datetime
from fastapi import FastAPI, WebSocket, APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn
from supabase import create_client

from glyx.mcp.websocket_manager import manager as ws_manager
from glyx.core.agent import ComposableAgent, AgentKey
from glyx.mcp.types import (
    StreamCursorRequest,
    AgentResponse,
    OrganizationCreate,
    OrganizationResponse,
    SaveMemoryRequest,
    SearchMemoryRequest,
)
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


# Create FastAPI app for additional routes (WebSocket, streaming, health)
api_app = FastAPI()

# API router with /api prefix
api_router = APIRouter(prefix="/api")


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


@api_router.get("/features")
async def api_list_features(status: str | None = None) -> list[Feature]:
    """List all features."""
    return list_features(status)


@api_router.post("/features")
async def api_create_feature(body: FeatureCreate) -> Feature:
    """Create a new feature with default pipeline stages."""
    pipeline = Pipeline.create(body)
    return save_feature(pipeline.feature)


@api_router.get("/features/{feature_id}")
async def api_get_feature(feature_id: str) -> Feature:
    """Get a feature by ID."""
    feature = get_feature(feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")
    return feature


@api_router.patch("/features/{feature_id}")
async def api_update_feature(feature_id: str, body: FeatureUpdate) -> Feature:
    """Update a feature."""
    feature = get_feature(feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")
    updated = feature.model_copy(update=body.model_dump(exclude_unset=True))
    return save_feature(updated)


@api_router.delete("/features/{feature_id}")
async def api_delete_feature(feature_id: str) -> dict[str, str]:
    """Delete a feature."""
    if not delete_feature(feature_id):
        raise HTTPException(status_code=404, detail="Feature not found")
    return {"status": "deleted"}


# Organization API (Supabase-backed)
DEFAULT_PROJECT_ID = "a0000000-0000-0000-0000-000000000001"


def get_supabase():
    """Get Supabase client."""
    url = settings.supabase_url
    key = settings.supabase_anon_key
    if not url or not key:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    return create_client(url, key)


@api_router.get("/organizations")
async def api_list_organizations() -> list[OrganizationResponse]:
    """List all organizations from Supabase."""
    client = get_supabase()
    response = client.table("organizations").select("*").eq("project_id", DEFAULT_PROJECT_ID).order("created_at", desc=True).execute()
    return [OrganizationResponse(**{**row, "id": str(row["id"])}) for row in response.data]


@api_router.post("/organizations")
async def api_create_organization(body: OrganizationCreate) -> OrganizationResponse:
    """Create a new organization in Supabase."""
    client = get_supabase()
    data = {
        "project_id": DEFAULT_PROJECT_ID,
        "name": body.name,
        "description": body.description,
        "template": body.template,
        "config": body.config,
        "status": "draft",
        "stages": [],
    }
    response = client.table("organizations").insert(data).execute()
    row = response.data[0]
    return OrganizationResponse(**{**row, "id": str(row["id"])})


@api_router.get("/organizations/{org_id}")
async def api_get_organization(org_id: str) -> OrganizationResponse:
    """Get an organization by ID."""
    client = get_supabase()
    response = client.table("organizations").select("*").eq("id", org_id).single().execute()
    row = response.data
    return OrganizationResponse(**{**row, "id": str(row["id"])})


@api_router.delete("/organizations/{org_id}")
async def api_delete_organization(org_id: str) -> dict[str, str]:
    """Delete an organization."""
    client = get_supabase()
    client.table("organizations").delete().eq("id", org_id).execute()
    return {"status": "deleted"}


@api_router.post("/memory/save")
async def api_save_memory(body: SaveMemoryRequest) -> dict[str, str]:
    """Save memory via REST endpoint."""
    run_id = body.run_id or f"dashboard-{int(datetime.now().timestamp())}"
    result = save_memory(
        content=body.content,
        agent_id=body.agent_id,
        run_id=run_id,
        category=body.category,  # type: ignore
        directory_name=body.directory_name,
    )
    return {"status": "saved", "result": result}


@api_router.post("/memory/search")
async def api_search_memory(body: SearchMemoryRequest) -> dict[str, list]:
    """Search memory via REST endpoint."""
    result = search_memory(
        query=body.query,
        category=body.category,  # type: ignore
        limit=body.limit,
    )
    import json
    memories = json.loads(result) if result else []
    return {"memories": memories}


@api_router.get("/agents")
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


# Include API router after all routes are defined
api_app.include_router(api_router)


async def main_http() -> None:
    """Run HTTP server with both MCP protocol and REST API."""
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting combined MCP + API server on http://0.0.0.0:{port}")

    # Create MCP ASGI app with proper path
    mcp_app = mcp.http_app(path='/mcp')

    # Combine MCP and REST routes with proper lifespan
    combined_app = FastAPI(
        title="Glyx MCP + REST API",
        routes=[
            *mcp_app.routes,    # MCP protocol at /mcp
            *api_app.routes,    # REST API routes
        ],
        lifespan=mcp_app.lifespan,  # Essential for MCP session management
    )

    # Add CORS middleware to combined app
    combined_app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    config = uvicorn.Config(combined_app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        asyncio.run(main_http())
    else:
        main()

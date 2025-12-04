"""FastMCP server for coding agents with Aider integration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import APIRouter, FastAPI, Header, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastmcp import Context, FastMCP
from fastmcp.utilities.logging import get_logger
from langfuse import Langfuse
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor
from openai import AsyncOpenAI
from supabase import create_client

from glyx.core.agent import AgentKey, ComposableAgent
from glyx.core.pipelines import (
    Feature,
    FeatureCreate,
    FeatureUpdate,
    Pipeline,
    delete_feature,
    get_feature,
    list_features,
    save_feature,
)
from glyx.core.registry import discover_and_register_agents
from glyx.mcp.models.response import BaseResponseEvent, StreamEventType, parse_response_event
from glyx.mcp.orchestration.orchestrator import Orchestrator
from glyx.mcp.settings import settings
from glyx.mcp.tools.agent_crud import (
    create_agent,
    delete_agent,
    get_agent,
    list_agents,
)
from glyx.mcp.tools.interact_with_user import ask_user
from glyx.mcp.tools.session_tools import (
    get_session_messages,
    list_sessions,
)
from glyx.mcp.tools.use_memory import (
    save_memory,
    search_memory,
)
from glyx.mcp.types import (
    AgentResponse,
    AuthResponse,
    AuthSignInRequest,
    AuthSignUpRequest,
    MemoryInferRequest,
    MemoryInferResponse,
    MemorySuggestion,
    OrganizationCreate,
    OrganizationResponse,
    SaveMemoryRequest,
    SearchMemoryRequest,
    SmartTaskRequest,
    StreamCursorRequest,
    TaskResponse,
)
from glyx.mcp.webhooks.github import create_github_webhook_router
from glyx.mcp.websocket_manager import manager as ws_manager

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


def _wrap_agent_event(event_payload: Any, timestamp: str | None) -> dict[str, Any]:
    base = {"type": StreamEventType.AGENT_EVENT.value, "event": event_payload}
    match timestamp:
        case str() as ts:
            return {**base, "timestamp": ts}
        case _:
            return base


def _normalize_inner_event(inner_event: Any) -> Any:
    match inner_event:
        case BaseResponseEvent() as typed:
            return typed.model_dump(mode="json")
        case dict() as mapping:
            return parse_response_event(mapping).model_dump(mode="json")
        case _:
            return inner_event


def _normalize_stream_payload(event: Any) -> Any:
    match event:
        case {"type": StreamEventType.AGENT_EVENT.value, "event": BaseResponseEvent() as typed, "timestamp": timestamp}:
            return _wrap_agent_event(typed.model_dump(mode="json"), timestamp)
        case {"type": StreamEventType.AGENT_EVENT.value, "event": BaseResponseEvent() as typed}:
            return _wrap_agent_event(typed.model_dump(mode="json"), None)
        case {"type": StreamEventType.AGENT_EVENT.value, "event": inner_event, "timestamp": timestamp}:
            return _wrap_agent_event(_normalize_inner_event(inner_event), timestamp)
        case {"type": StreamEventType.AGENT_EVENT.value, "event": inner_event}:
            return _wrap_agent_event(_normalize_inner_event(inner_event), None)
        case BaseResponseEvent() as typed:
            return _wrap_agent_event(typed.model_dump(mode="json"), None)
        case _:
            return event


@api_app.post("/stream/cursor")
async def stream_cursor(body: StreamCursorRequest) -> StreamingResponse:
    """Stream cursor agent output with real-time NDJSON events."""

    async def generate():
        try:
            prompt = body.prompt
            model = body.model

            yield f"data: {json.dumps({'type': StreamEventType.PROGRESS.value, 'message': '🚀 Starting cursor agent...', 'timestamp': datetime.now().isoformat()})}\n\n"

            agent = ComposableAgent.from_key(AgentKey.CURSOR)

            # Stream events in real-time (activity creation handled inside execute_stream)
            async for event in agent.execute_stream(
                {
                    "prompt": prompt,
                    "model": model,
                    "force": True,
                    "output_format": "stream-json",
                },
                timeout=600,
                org_id=body.organization_id,
                org_name=body.organization_name,
            ):
                normalized = _normalize_stream_payload(event)
                yield f"data: {json.dumps(normalized)}\n\n"

        except Exception as e:
            logger.exception("Stream cursor error")
            yield f"data: {json.dumps({'type': StreamEventType.ERROR.value, 'error': str(e), 'timestamp': datetime.now().isoformat()})}\n\n"

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


# Tasks API
SMART_TASK_SYSTEM_PROMPT = """You are a task creation assistant. Given selected text from a webpage, create a clear and actionable task.

Return a JSON object with:
- title: A concise task title (max 80 chars)
- description: A detailed description of what needs to be done

The task should be:
- Actionable and specific
- Based on the context provided
- Professional in tone

Return ONLY valid JSON, no markdown or explanation."""


def get_openrouter_client() -> AsyncOpenAI:
    """Get OpenRouter client."""
    api_key = settings.openrouter_api_key
    if not api_key:
        raise HTTPException(status_code=500, detail="OpenRouter API key not configured")
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


@api_router.get("/tasks")
async def api_list_tasks() -> list[TaskResponse]:
    """List all tasks from Supabase."""
    client = get_supabase()
    response = client.table("tasks").select("*").order("created_at", desc=True).execute()
    return [TaskResponse(**{**row, "id": str(row["id"])}) for row in response.data]


@api_router.post("/tasks")
async def api_create_task(body: dict) -> TaskResponse:
    """Create a new task in Supabase."""
    client = get_supabase()
    insert_data = {"title": body["title"], "description": body["description"], "status": body.get("status", "pending")}
    response = client.table("tasks").insert(insert_data).execute()
    row = response.data[0]
    return TaskResponse(**{**row, "id": str(row["id"])})


@api_router.get("/tasks/{task_id}")
async def api_get_task(task_id: str) -> TaskResponse:
    """Get a task by ID."""
    client = get_supabase()
    response = client.table("tasks").select("*").eq("id", task_id).single().execute()
    row = response.data
    return TaskResponse(**{**row, "id": str(row["id"])})


@api_router.patch("/tasks/{task_id}")
async def api_update_task(task_id: str, body: dict) -> TaskResponse:
    """Update a task."""
    client = get_supabase()
    update_data = {k: v for k, v in body.items() if v is not None}
    response = client.table("tasks").update(update_data).eq("id", task_id).execute()
    row = response.data[0]
    return TaskResponse(**{**row, "id": str(row["id"])})


@api_router.delete("/tasks/{task_id}")
async def api_delete_task(task_id: str) -> dict[str, str]:
    """Delete a task."""
    client = get_supabase()
    client.table("tasks").delete().eq("id", task_id).execute()
    return {"status": "deleted"}


@api_router.post("/tasks/smart")
async def api_create_smart_task(body: SmartTaskRequest) -> TaskResponse:
    """Create a task using AI to generate title and description from selected text."""
    if not body.selected_text.strip():
        raise HTTPException(status_code=400, detail="Selected text is required")

    # Build prompt with context
    user_prompt = f"""Create a task from this selected text:

Selected text: "{body.selected_text}"
{f'Page title: {body.page_title}' if body.page_title else ''}
{f'Source URL: {body.page_url}' if body.page_url else ''}

Return JSON with "title" and "description" fields."""

    # Call OpenRouter API
    openrouter = get_openrouter_client()
    try:
        response = await openrouter.chat.completions.create(
            model="anthropic/claude-sonnet-4",
            messages=[
                {"role": "system", "content": SMART_TASK_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=500,
        )
        ai_text = response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"OpenRouter API error: {e}")
        raise HTTPException(status_code=500, detail=f"AI generation failed: {e}")

    # Parse AI response
    try:
        import re
        cleaned = re.sub(r"```json\n?|\n?```", "", ai_text).strip()
        task_data = json.loads(cleaned)
        title = task_data.get("title", body.selected_text[:80])
        description = task_data.get("description", body.selected_text)
    except (json.JSONDecodeError, KeyError):
        # Fallback if AI returns malformed JSON
        title = body.selected_text[:80]
        description = f'Task created from: "{body.selected_text}"'

    # Add source URL to description
    full_description = f"{description}\n\nSource: {body.page_url}" if body.page_url else description

    # Create task in Supabase
    supabase = get_supabase()
    insert_data = {
        "title": title,
        "description": full_description,
        "status": "pending",
    }
    response = supabase.table("tasks").insert(insert_data).execute()
    row = response.data[0]

    return TaskResponse(
        id=str(row["id"]),
        title=row["title"],
        description=row["description"],
        status=row["status"],
        organization_id=row.get("organization_id"),
        created_at=row["created_at"],
    )


# Auth API (Supabase Auth)
@api_router.post("/auth/signup")
async def api_auth_signup(body: AuthSignUpRequest) -> AuthResponse:
    """Sign up a new user via Supabase Auth."""
    client = get_supabase()
    options = {"data": body.metadata} if body.metadata else None
    response = client.auth.sign_up({"email": body.email, "password": body.password, "options": options})
    user = response.user
    session = response.session
    return AuthResponse(
        user_id=user.id if user else None,
        email=user.email if user else None,
        access_token=session.access_token if session else None,
        refresh_token=session.refresh_token if session else None,
        expires_at=session.expires_at if session else None,
    )


@api_router.post("/auth/signin")
async def api_auth_signin(body: AuthSignInRequest) -> AuthResponse:
    """Sign in a user via Supabase Auth."""
    client = get_supabase()
    response = client.auth.sign_in_with_password({"email": body.email, "password": body.password})
    user = response.user
    session = response.session
    return AuthResponse(
        user_id=user.id if user else None,
        email=user.email if user else None,
        access_token=session.access_token if session else None,
        refresh_token=session.refresh_token if session else None,
        expires_at=session.expires_at if session else None,
    )


@api_router.post("/auth/signout")
async def api_auth_signout() -> dict[str, str]:
    """Sign out the current user."""
    client = get_supabase()
    client.auth.sign_out()
    return {"status": "signed_out"}


@api_router.get("/auth/user")
async def api_auth_get_user(authorization: str | None = Header(None)) -> AuthResponse:
    """Get the current user from JWT token."""
    client = get_supabase()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    jwt = authorization[7:]
    response = client.auth.get_user(jwt)
    user = response.user
    return AuthResponse(
        user_id=user.id if user else None,
        email=user.email if user else None,
    )


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
    memories = json.loads(result) if result else []
    return {"memories": memories}


@api_router.post("/memory/infer")
async def api_infer_memory(body: MemoryInferRequest) -> MemoryInferResponse:
    """Use AI to analyze page content and suggest memories to save.

    This endpoint:
    1. Searches existing memories for context
    2. Uses GPT to analyze the page content
    3. Suggests relevant memories to save based on what's new/useful
    """
    client = AsyncOpenAI()

    # Search existing memories for context
    existing_context = ""
    if body.page_title:
        existing_result = search_memory(query=body.page_title, limit=5)
        existing_memories = json.loads(existing_result) if existing_result else []
        if existing_memories:
            existing_context = "\n".join(
                f"- {m.get('memory', '')}" for m in existing_memories[:5]
            )

    system_prompt = """You are a knowledge extraction assistant. Analyze the provided page content and suggest 2-4 specific, actionable memories worth saving.

Focus on:
- Technical patterns, APIs, or code examples
- Architecture decisions or best practices
- Key concepts or definitions
- Useful commands or configurations

For each suggestion:
1. Extract the core information (be concise, 1-2 sentences)
2. Assign a category: architecture, integrations, code_style_guidelines, project_id, observability, product, key_concept, or tasks
3. Explain why this is worth remembering

Respond in JSON format:
{
  "analysis": "Brief summary of what the page is about",
  "suggestions": [
    {"content": "...", "category": "...", "reason": "..."}
  ]
}"""

    user_prompt = f"""Page: {body.page_title or 'Unknown'}
URL: {body.page_url or 'N/A'}
User context: {body.user_context or 'None provided'}

Existing memories (avoid duplicating):
{existing_context or 'None'}

Page content:
{body.page_content[:8000]}"""

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    result_text = response.choices[0].message.content or "{}"
    result_data = json.loads(result_text)

    suggestions = [
        MemorySuggestion(**s) for s in result_data.get("suggestions", [])
    ]

    return MemoryInferResponse(
        suggestions=suggestions,
        analysis=result_data.get("analysis", "Unable to analyze content"),
    )


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

# Include webhook router
webhook_router = create_github_webhook_router(get_supabase)
api_app.include_router(webhook_router)


async def main_http() -> None:
    """Run HTTP server with both MCP protocol and REST API."""
    port = int(os.environ.get("PORT", 8000))
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
    # Note: Chrome extensions use chrome-extension:// origins which can't be allowlisted
    # We use allow_origin_regex to permit them along with localhost
    combined_app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_origin_regex=r"^chrome-extension://.*$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    config = uvicorn.Config(combined_app, host="0.0.0.0", port=port, log_level="debug")
    server = uvicorn.Server(config)
    await server.serve()


def run_http() -> None:
    """Entry point for HTTP server command."""
    asyncio.run(main_http())


if __name__ == "__main__":
    asyncio.run(main_http())

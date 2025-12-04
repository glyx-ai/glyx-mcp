"""FastMCP server for coding agents with Aider integration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from time import time
from typing import Any

import uvicorn
from fastapi import APIRouter, FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastmcp import Context, FastMCP
from fastmcp.utilities.logging import get_logger
from langfuse import Langfuse
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor
from openai import AsyncOpenAI
from supabase import create_client

from glyx_python_sdk import (
    ComposableAgent,
    AgentSequence,
    AgentSequenceCreate,
    AgentSequenceUpdate,
    Pipeline,
    delete_agent_sequence,
    get_agent_sequence,
    list_agent_sequences,
    save_agent_sequence,
    discover_and_register_agents,
    GlyxOrchestrator,
    settings,
    save_memory,
    search_memory,
)
from glyx_python_sdk.workflows import (
    AgentWorkflowConfig,
    AgentWorkflowCreate,
    AgentWorkflowUpdate,
    AgentWorkflowExecuteRequest,
    delete_workflow,
    get_workflow,
    list_workflows,
    save_workflow,
)
from glyx_python_sdk.models.response import BaseResponseEvent, StreamEventType, parse_response_event
from glyx_python_sdk.types import (
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
from glyx_python_sdk.websocket_manager import manager as ws_manager
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
from glyx.mcp.webhooks.github import create_github_webhook_router
from glyx.mcp.webhooks.linear import create_linear_webhook_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
    ],
    force=True,
)

logger = logging.getLogger(__name__)

# Track server start time for uptime metrics
start_time = time()


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
to_client_logger.setLevel(level=logging.INFO)


mcp = FastMCP("glyx-mcp")

# Register tools with MCP server
logger.info("Initializing MCP tools...")

# Auto-discover and register agents from JSON configs
# Agents are now in the SDK package
from pathlib import Path as PathLibPath
import glyx_python_sdk

# Get agents directory from SDK package location
_sdk_path = PathLibPath(glyx_python_sdk.__file__).parent.parent
agents_dir = _sdk_path / "agents"
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
    from agents.items import ItemHelpers, MessageOutputItem

    logger.info(f"orchestrate tool received - task: {task!r}")

    orchestrator = GlyxOrchestrator(
        agent_name="MCPOrchestrator",
        model="openrouter/anthropic/claude-sonnet-4",
        mcp_servers=[],
        session_id="mcp-orchestrate",
    )

    try:
        output_parts = []
        async for item in orchestrator.run_prompt_streamed_items(task):
            if isinstance(item, MessageOutputItem):
                text = ItemHelpers.text_message_output(item)
                output_parts.append(text)

        await orchestrator.cleanup()
        return f"✅ Orchestration completed successfully\n\n{''.join(output_parts)}"
    except Exception as e:
        logger.error(f"Orchestration failed: {e}")
        return f"❌ Orchestration failed: {e}"


def main() -> None:
    """Run the FastMCP server (stdio mode for Claude Code)."""
    mcp.run()


# Create FastAPI app for additional routes (WebSocket, streaming, health)
api_app = FastAPI(
    title="Glyx MCP API",
    description="""
# Glyx MCP API

Composable AI agent framework with FastMCP server integration.

## Features

- **Multi-Agent Orchestration**: Coordinate multiple AI agents for complex tasks
- **Real-time Streaming**: WebSocket and SSE support for live updates
- **Memory Management**: Store and retrieve project context with semantic search
- **Feature Pipelines**: Multi-stage workflows for feature development
- **Task Management**: AI-powered task creation and tracking
- **Organization Management**: Multi-tenant support with Supabase
- **Health Monitoring**: Comprehensive health checks and metrics

## Authentication

Most endpoints require authentication via Supabase Auth. Include the access token in the Authorization header:

```
Authorization: Bearer <access_token>
```

## Environment Setup

Required environment variables:
- `OPENAI_API_KEY` - OpenAI API key
- `ANTHROPIC_API_KEY` - Anthropic API key
- `OPENROUTER_API_KEY` - OpenRouter API key
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_ANON_KEY` - Supabase anon key
- `MEM0_API_KEY` - Mem0 API key for memory management

## Resources

- [GitHub Repository](https://github.com/htelsiz/glyx-mcp)
- [SDK Documentation](https://github.com/htelsiz/glyx-mcp/blob/main/docs/SDK.md)
- [Deployment Guide](https://github.com/htelsiz/glyx-mcp/blob/main/docs/DEPLOYMENT.md)
    """,
    version="0.1.0",
    contact={
        "name": "Glyx Team",
        "url": "https://github.com/htelsiz/glyx-mcp",
        "email": "hakantelsiz@utexas.edu",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=[
        {
            "name": "Health",
            "description": "Health check and monitoring endpoints",
        },
        {
            "name": "Streaming",
            "description": "Real-time streaming endpoints for agent execution",
        },
        {
            "name": "Features",
            "description": "Feature pipeline management for multi-stage development workflows",
        },
        {
            "name": "Organizations",
            "description": "Organization management with Supabase backend",
        },
        {
            "name": "Tasks",
            "description": "Task creation and management, including AI-powered smart tasks",
        },
        {
            "name": "Authentication",
            "description": "User authentication via Supabase Auth",
        },
        {
            "name": "Memory",
            "description": "Project memory management with semantic search (Mem0)",
        },
        {
            "name": "Agents",
            "description": "Agent execution and management",
        },
        {
            "name": "GitHub",
            "description": "GitHub integration and repository management",
        },
        {
            "name": "Linear",
            "description": "Linear integration for issue tracking",
        },
    ],
)

# Mount static files
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    api_app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


# API router with /api prefix
api_router = APIRouter(prefix="/api")


@api_app.get("/")
async def root():
    """Serve the repository deployment interface."""
    static_path = Path(__file__).parent.parent / "static" / "index.html"
    if static_path.exists():
        return FileResponse(str(static_path))
    else:
        raise HTTPException(status_code=404, detail="UI not found")


@api_router.get("/healthz", tags=["Health"], summary="Basic Health Check", response_description="Service health status")
async def healthz() -> dict[str, Any]:
    """
    Basic health check endpoint for load balancers and monitoring.

    Returns a simple status indicating the service is running.

    **Returns:**
    - `status`: "ok" if service is healthy
    - `timestamp`: Current server timestamp (ISO 8601)
    - `service`: Service name

    **Example Response:**
    ```json
    {
        "status": "ok",
        "timestamp": "2025-12-04T13:45:00.000Z",
        "service": "glyx-mcp"
    }
    ```
    """
    return {"status": "ok", "timestamp": datetime.now().isoformat(), "service": "glyx-mcp"}


@api_router.get(
    "/health/detailed",
    tags=["Health"],
    summary="Detailed Health Check",
    response_description="Comprehensive service health status with component checks",
)
async def health_detailed() -> dict[str, Any]:
    """
    Detailed health check including status of all integrated services.

    Checks connectivity and configuration for:
    - Supabase (database)
    - Langfuse (tracing)
    - OpenAI (API integration)
    - Anthropic (API integration)
    - OpenRouter (API integration)

    **Status Values:**
    - `healthy`: All systems operational
    - `degraded`: Some services unavailable but core functionality works
    - `unhealthy`: Critical services down

    **Example Response:**
    ```json
    {
        "status": "healthy",
        "timestamp": "2025-12-04T13:45:00.000Z",
        "service": "glyx-mcp",
        "checks": {
            "supabase": {"status": "ok", "message": "Connected"},
            "langfuse": {"status": "ok", "message": "Connected"},
            "openai": {"status": "configured"},
            "anthropic": {"status": "configured"},
            "openrouter": {"status": "configured"}
        }
    }
    ```
    """
    checks: dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "glyx-mcp",
        "checks": {},
    }

    # Check Supabase connection
    if settings.supabase_url and settings.supabase_anon_key:
        try:
            client = get_supabase()
            client.table("organizations").select("id").limit(1).execute()
            checks["checks"]["supabase"] = {"status": "ok", "message": "Connected"}
        except Exception as e:
            checks["checks"]["supabase"] = {"status": "error", "message": str(e)}
            checks["status"] = "degraded"
    else:
        checks["checks"]["supabase"] = {"status": "not_configured"}

    # Check Langfuse connection
    if langfuse:
        try:
            langfuse.auth_check()
            checks["checks"]["langfuse"] = {"status": "ok", "message": "Connected"}
        except Exception as e:
            checks["checks"]["langfuse"] = {"status": "error", "message": str(e)}
            checks["status"] = "degraded"
    else:
        checks["checks"]["langfuse"] = {"status": "not_configured"}

    # Check OpenAI API key
    checks["checks"]["openai"] = {"status": "configured" if settings.openai_api_key else "not_configured"}

    # Check Anthropic API key
    checks["checks"]["anthropic"] = {"status": "configured" if settings.anthropic_api_key else "not_configured"}

    # Check OpenRouter API key
    checks["checks"]["openrouter"] = {"status": "configured" if settings.openrouter_api_key else "not_configured"}

    return checks


@api_router.get(
    "/metrics", tags=["Health"], summary="Service Metrics", response_description="Prometheus-compatible metrics"
)
async def metrics() -> dict[str, Any]:
    """
    Prometheus-compatible metrics for monitoring and alerting.

    **Metrics:**
    - `uptime_seconds`: Time since server start
    - `agents_available`: Number of configured agents

    **Example Response:**
    ```json
    {
        "timestamp": "2025-12-04T13:45:00.000Z",
        "service": "glyx-mcp",
        "uptime_seconds": 3600.5,
        "agents_available": 8
    }
    ```
    """
    return {
        "timestamp": datetime.now().isoformat(),
        "service": "glyx-mcp",
        "uptime_seconds": time() - start_time,
        "agents_available": len(list(agents_dir.glob("*.json"))),
    }


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


@api_app.post(
    "/stream/cursor",
    tags=["Streaming"],
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
    - `organization_id`: Organization UUID
    - `organization_name`: Organization name (optional)

    **Example Event:**
    ```
    data: {"type": "message", "content": "Implementing authentication...", "timestamp": "2025-12-04T13:45:00.000Z"}
    ```

    **Usage:**
    ```javascript
    const eventSource = new EventSource('/stream/cursor', {
        method: 'POST',
        body: JSON.stringify({task: {...}, organization_id: '...'})
    });
    eventSource.onmessage = (e) => {
        const data = JSON.parse(e.data);
        console.log(data.type, data.content);
    };
    ```
    """
    from agents.items import ItemHelpers, MessageOutputItem, ToolCallItem, ToolCallOutputItem, ReasoningItem

    from glyx_python_sdk.agent import create_event
    from glyx_python_sdk import build_task_prompt

    async def publish(event_type: str, content: str, metadata: dict | None = None):
        """Publish event to Supabase."""
        await create_event(
            org_id=body.organization_id,
            type=event_type,
            content=content,
            org_name=body.organization_name,
            metadata=metadata,
        )

    async def generate():
        try:
            prompt = build_task_prompt(body.task)
            logger.info(f"[STREAM] Executing task {body.task.id}: {body.task.title}")

            yield f"data: {json.dumps({'type': 'progress', 'message': '🚀 Starting orchestrator...', 'timestamp': datetime.now().isoformat()})}\n\n"

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
                        await publish("tool_call", f"Tool: {item.raw_item.name}", {"tool_name": item.raw_item.name})
                        yield f"data: {json.dumps({'type': 'tool_call', 'tool': item.raw_item.name, 'timestamp': timestamp})}\n\n"

                    case ToolCallOutputItem() as item:
                        yield f"data: {json.dumps({'type': 'tool_output', 'output': str(item.output)[:500], 'timestamp': timestamp})}\n\n"

                    case MessageOutputItem() as item:
                        text = ItemHelpers.text_message_output(item)
                        await publish("message", text)
                        yield f"data: {json.dumps({'type': 'message', 'content': text, 'timestamp': timestamp})}\n\n"

                    case ReasoningItem() as item:
                        await publish("thinking", str(item.raw_item)[:500])
                        yield f"data: {json.dumps({'type': 'thinking', 'content': str(item.raw_item), 'timestamp': timestamp})}\n\n"

            await publish("complete", "Task completed")
            yield f"data: {json.dumps({'type': 'complete', 'output': 'Task completed', 'timestamp': datetime.now().isoformat()})}\n\n"

            await orchestrator.cleanup()

        except Exception as e:
            logger.exception("Stream cursor error")
            await publish("error", str(e))
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


@api_router.get(
    "/agent-sequences",
    tags=["Agent Sequences"],
    summary="List Agent Sequences",
    response_description="List of agent sequences",
)
async def api_list_agent_sequences(status: str | None = None) -> list[AgentSequence]:
    """
    List all agent sequences, optionally filtered by status.

    **Query Parameters:**
    - `status` (optional): Filter by status ("in_progress", "review", "testing", "done")

    **Returns:** Array of AgentSequence objects with stages, artifacts, and conversation history
    """
    return list_agent_sequences(status)


@api_router.post(
    "/agent-sequences",
    tags=["Agent Sequences"],
    summary="Create Agent Sequence",
    response_description="Created agent sequence with default pipeline",
    status_code=201,
)
async def api_create_agent_sequence(body: AgentSequenceCreate) -> AgentSequence:
    """
    Create a new agent sequence with default 3-stage pipeline.

    Creates an agent sequence with:
    1. **Implementation** stage (CODER role with CURSOR agent)
    2. **Code Review** stage (REVIEWER role with CLAUDE agent)
    3. **Testing** stage (QA role with CLAUDE agent)

    **Request Body:**
    - `name`: Sequence name
    - `description`: Sequence description

    **Example:**
    ```json
    {
        "name": "User Authentication",
        "description": "JWT-based authentication with refresh tokens"
    }
    ```
    """
    pipeline = Pipeline.create(body)
    return save_agent_sequence(pipeline.agent_sequence)


@api_router.get("/agent-sequences/{sequence_id}")
async def api_get_agent_sequence(sequence_id: str) -> AgentSequence:
    """Get an agent sequence by ID."""
    agent_sequence = get_agent_sequence(sequence_id)
    if not agent_sequence:
        raise HTTPException(status_code=404, detail="Agent sequence not found")
    return agent_sequence


@api_router.patch("/agent-sequences/{sequence_id}")
async def api_update_agent_sequence(sequence_id: str, body: AgentSequenceUpdate) -> AgentSequence:
    """Update an agent sequence."""
    agent_sequence = get_agent_sequence(sequence_id)
    if not agent_sequence:
        raise HTTPException(status_code=404, detail="Agent sequence not found")
    updated = agent_sequence.model_copy(update=body.model_dump(exclude_unset=True))
    return save_agent_sequence(updated)


@api_router.delete("/agent-sequences/{sequence_id}")
async def api_delete_agent_sequence(sequence_id: str) -> dict[str, str]:
    """Delete an agent sequence."""
    if not delete_agent_sequence(sequence_id):
        raise HTTPException(status_code=404, detail="Agent sequence not found")
    return {"status": "deleted"}


# Agent Workflows API (Composable API Agent)
@api_router.get("/agent-workflows", tags=["Agent Workflows"], summary="List Agent Workflows")
async def api_list_workflows(user_id: str | None = None) -> list[AgentWorkflowConfig]:
    """
    List all agent workflows, optionally filtered by user.

    **Query Parameters:**
    - `user_id` (optional): Filter by user ID (omit for global workflows)

    **Returns:** Array of AgentWorkflowConfig objects matching agents/*.json structure
    """
    return list_workflows(user_id)


@api_router.post(
    "/agent-workflows",
    tags=["Agent Workflows"],
    summary="Create Agent Workflow",
    status_code=201,
)
async def api_create_workflow(body: AgentWorkflowCreate) -> AgentWorkflowConfig:
    """
    Create a new agent workflow with JSON config structure.

    Creates a custom agent similar to agents/*.json files but stored in database.

    **Request Body:**
    - `agent_key`: Unique identifier for this agent
    - `command`: CLI command to execute
    - `args`: Dict of argument specifications (flag, type, required, default, description)
    - `description` (optional): Human-readable description
    - `version` (optional): Version string
    - `capabilities` (optional): List of capability tags

    **Example:**
    ```json
    {
        "agent_key": "my_custom_agent",
        "command": "python",
        "args": {
            "script": {
                "flag": "",
                "type": "string",
                "required": true,
                "description": "Python script to run"
            },
            "verbose": {
                "flag": "--verbose",
                "type": "bool",
                "required": false,
                "default": false
            }
        },
        "description": "Custom Python script executor"
    }
    ```
    """
    workflow = AgentWorkflowConfig(**body.model_dump())
    return save_workflow(workflow)


@api_router.get("/agent-workflows/{workflow_id}")
async def api_get_workflow(workflow_id: str) -> AgentWorkflowConfig:
    """Get an agent workflow by ID."""
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@api_router.patch("/agent-workflows/{workflow_id}")
async def api_update_workflow(workflow_id: str, body: AgentWorkflowUpdate) -> AgentWorkflowConfig:
    """Update an agent workflow."""
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    updated = workflow.model_copy(update=body.model_dump(exclude_unset=True))
    return save_workflow(updated)


@api_router.delete("/agent-workflows/{workflow_id}")
async def api_delete_workflow(workflow_id: str) -> dict[str, str]:
    """Delete an agent workflow."""
    if not delete_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"status": "deleted"}


@api_router.post("/agent-workflows/{workflow_id}/execute")
async def api_execute_workflow(workflow_id: str, body: AgentWorkflowExecuteRequest) -> dict[str, Any]:
    """
    Execute a custom agent workflow.

    **Path Parameters:**
    - `workflow_id`: ID of the workflow to execute

    **Request Body:**
    - `task_config`: Task configuration (e.g., {"prompt": "...", "files": "..."})
    - `timeout` (optional): Execution timeout in seconds (default: 120, max: 600)

    **Returns:** Agent execution result with stdout, stderr, exit_code, success
    """
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    agent = workflow.to_composable_agent()
    result = await agent.execute(body.task_config, timeout=body.timeout)

    return {
        "success": result.success,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "execution_time": result.execution_time,
        "timed_out": result.timed_out,
    }


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
    response = (
        client.table("organizations")
        .select("*")
        .eq("project_id", DEFAULT_PROJECT_ID)
        .order("created_at", desc=True)
        .execute()
    )
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
    insert_data = {
        "title": body["title"],
        "description": body["description"],
        "organization_id": body["organization_id"],
        "status": "in_progress",
        "assigned_at": datetime.now().isoformat(),
    }
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


@api_router.get("/tasks/linear/{session_id}")
async def api_get_linear_task(session_id: str) -> TaskResponse | None:
    """Get a task by Linear session ID."""
    client = get_supabase()
    response = (
        client.table("tasks")
        .select("*")
        .eq("linear_session_id", session_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not response.data:
        return None
    row = response.data[0]
    return TaskResponse(**{**row, "id": str(row["id"])})


@api_router.get("/tasks/linear/workspace/{workspace_id}")
async def api_list_linear_tasks(workspace_id: str) -> list[TaskResponse]:
    """List all tasks for a Linear workspace."""
    client = get_supabase()
    response = (
        client.table("tasks")
        .select("*")
        .eq("linear_workspace_id", workspace_id)
        .order("created_at", desc=True)
        .execute()
    )
    return [TaskResponse(**{**row, "id": str(row["id"])}) for row in response.data]


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


@api_router.post(
    "/tasks/smart",
    tags=["Tasks"],
    summary="Create Smart Task",
    response_description="AI-generated task from selected text",
    status_code=201,
)
async def api_create_smart_task(body: SmartTaskRequest) -> TaskResponse:
    """
    Create a task using AI to generate title and description from selected text.

    Uses Claude Sonnet 4 via OpenRouter to analyze the selected text and create
    a well-structured, actionable task with appropriate title and description.

    **Request Body:**
    - `selected_text`: Text selected by user (required)
    - `page_title`: Title of the source page (optional)
    - `page_url`: URL of the source page (optional)

    **Example:**
    ```json
    {
        "selected_text": "Implement JWT authentication with refresh tokens",
        "page_title": "Security Best Practices",
        "page_url": "https://example.com/security"
    }
    ```

    **Response:** Task object with AI-generated title and description
    """
    if not body.selected_text.strip():
        raise HTTPException(status_code=400, detail="Selected text is required")

    # Build prompt with context
    user_prompt = f"""Create a task from this selected text:

Selected text: "{body.selected_text}"
{f"Page title: {body.page_title}" if body.page_title else ""}
{f"Source URL: {body.page_url}" if body.page_url else ""}

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


@api_router.post(
    "/memory/infer",
    tags=["Memory"],
    summary="Infer Memories from Page Content",
    response_description="AI-suggested memories to save",
)
async def api_infer_memory(body: MemoryInferRequest) -> MemoryInferResponse:
    """
    Use AI to analyze page content and suggest relevant memories to save.

    This endpoint uses GPT-4o-mini to:

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
            existing_context = "\n".join(f"- {m.get('memory', '')}" for m in existing_memories[:5])

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

    user_prompt = f"""Page: {body.page_title or "Unknown"}
URL: {body.page_url or "N/A"}
User context: {body.user_context or "None provided"}

Existing memories (avoid duplicating):
{existing_context or "None"}

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

    suggestions = [MemorySuggestion(**s) for s in result_data.get("suggestions", [])]

    return MemoryInferResponse(
        suggestions=suggestions,
        analysis=result_data.get("analysis", "Unable to analyze content"),
    )


@api_router.get("/agents")
async def api_list_agents() -> list[AgentResponse]:
    """List all available agents from JSON configs."""
    agents_path = agents_dir
    result: list[AgentResponse] = []

    for json_file in agents_path.glob("*.json"):
        try:
            agent = ComposableAgent.from_file(json_file)
            config = agent.config
            model_arg = config.args.get("model")
            model_default = model_arg.default if model_arg and model_arg.default else "gpt-5"
            result.append(
                AgentResponse(
                    name=config.agent_key,
                    model=str(model_default),
                    description=config.description or f"Execute {config.agent_key} agent",
                    capabilities=config.capabilities,
                    status="online",
                )
            )
        except Exception as e:
            logger.warning(f"Failed to load agent from {json_file}: {e}")
            continue

    return result


@api_router.get("/deployments")
async def api_list_deployments(
    authorization: str | None = Header(None),
    status: str | None = None,
    owner: str | None = None,
) -> list[dict]:
    """List deployments, optionally filtered by status or owner."""
    try:
        supabase = get_supabase()
        query = supabase.table("deployments").select("*")

        if status:
            query = query.eq("status", status)
        if owner:
            query = query.eq("owner", owner)

        response = query.order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        logger.error(f"Failed to list deployments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/deployments/{deployment_id}")
async def api_get_deployment(
    deployment_id: str,
    authorization: str | None = Header(None),
) -> dict:
    """Get specific deployment details."""
    try:
        supabase = get_supabase()
        response = supabase.table("deployments").select("*").eq("id", deployment_id).single().execute()
        return response.data
    except Exception as e:
        logger.error(f"Failed to get deployment: {e}")
        raise HTTPException(status_code=404, detail=str(e))


@api_router.patch("/deployments/{deployment_id}")
async def api_update_deployment(
    deployment_id: str,
    body: dict,
    authorization: str | None = Header(None),
) -> dict:
    """Update deployment status or configuration."""
    try:
        supabase = get_supabase()
        update_data = {k: v for k, v in body.items() if v is not None}
        if "status" in update_data and update_data["status"] == "deployed":
            update_data["deployed_at"] = datetime.now().isoformat()

        response = supabase.table("deployments").update(update_data).eq("id", deployment_id).execute()
        return response.data[0]
    except Exception as e:
        logger.error(f"Failed to update deployment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/deployments/{deployment_id}")
async def api_delete_deployment(
    deployment_id: str,
    authorization: str | None = Header(None),
) -> dict[str, str]:
    """Delete a deployment."""
    try:
        supabase = get_supabase()
        supabase.table("deployments").delete().eq("id", deployment_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        logger.error(f"Failed to delete deployment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get(
    "/github/repositories",
    tags=["GitHub"],
    summary="List GitHub Repositories",
    response_description="List of GitHub repositories from activity history",
)
async def api_list_github_repositories() -> list[dict[str, Any]]:
    """
    List unique GitHub repositories from activity history.

    Returns repositories that have had webhook events (pushes, PRs, issues, etc.)
    stored in the activities table. Repositories are identified by org_id in the
    format "owner/repo".

    **Returns:** Array of repository objects with:
    - `full_name`: Repository full name (e.g., "owner/repo")
    - `owner`: Repository owner/organization name
    - `name`: Repository name
    - `last_activity`: Most recent activity timestamp (ISO format)

    **Example Response:**
    ```json
    [
        {
            "full_name": "htelsiz/glyx-mcp",
            "owner": "htelsiz",
            "name": "glyx-mcp",
            "last_activity": "2025-12-04T13:45:00.000Z"
        }
    ]
    ```
    """
    try:
        supabase = get_supabase()
        # Query activities table for unique org_ids that look like GitHub repos (contain "/")
        # Note: The table was renamed to "events" in migration but code still uses "activities"
        response = (
            supabase.table("activities")
            .select("org_id, org_name, created_at")
            .not_.is_("org_id", "null")
            .order("created_at", desc=True)
            .execute()
        )

        # Extract unique repositories (org_id format: "owner/repo")
        repos: dict[str, dict[str, Any]] = {}
        for row in response.data:
            org_id = row.get("org_id", "")
            if isinstance(org_id, str) and "/" in org_id:
                if org_id not in repos:
                    parts = org_id.split("/", 1)
                    repos[org_id] = {
                        "full_name": org_id,
                        "owner": parts[0] if len(parts) > 0 else "",
                        "name": parts[1] if len(parts) > 1 else org_id,
                        "last_activity": row.get("created_at"),
                    }
                else:
                    # Update last_activity if this is more recent
                    current_time = row.get("created_at")
                    if current_time and (
                        not repos[org_id]["last_activity"] or current_time > repos[org_id]["last_activity"]
                    ):
                        repos[org_id]["last_activity"] = current_time

        # Sort by last activity (most recent first)
        repo_list = sorted(
            repos.values(),
            key=lambda x: x.get("last_activity", ""),
            reverse=True,
        )

        return repo_list
    except Exception as e:
        logger.error(f"Failed to list GitHub repositories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Include API router after all routes are defined
api_app.include_router(api_router)

# Include webhook routers
github_webhook_router = create_github_webhook_router(get_supabase)
linear_webhook_router = create_linear_webhook_router(get_supabase)
api_app.include_router(github_webhook_router)
api_app.include_router(linear_webhook_router)


async def main_http() -> None:
    """Run HTTP server with both MCP protocol and REST API."""
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting combined MCP + API server on http://0.0.0.0:{port}")

    # Create MCP ASGI app with proper path
    mcp_app = mcp.http_app(path="/mcp")

    # Combine MCP and REST routes with proper lifespan
    combined_app = FastAPI(
        title="Glyx MCP + REST API",
        description=api_app.description,
        version=api_app.version,
        contact=api_app.contact,
        license_info=api_app.license_info,
        openapi_tags=api_app.openapi_tags,
        routes=[
            *mcp_app.routes,  # MCP protocol at /mcp
            *api_app.routes,  # REST API routes
        ],
        lifespan=mcp_app.lifespan,  # Essential for MCP session management
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Exception handlers must be on combined_app (not api_app) to work
    @combined_app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.error(f"[VALIDATION ERROR] {request.method} {request.url.path}")
        for error in exc.errors():
            logger.error(f"  {error['loc']}: {error['msg']} (type={error['type']})")
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @combined_app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.exception(f"[UNHANDLED ERROR] {request.method} {request.url.path}: {exc}")
        return JSONResponse(status_code=500, content={"detail": str(exc)})

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

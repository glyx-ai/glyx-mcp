"""Combined FastAPI server for MCP protocol and REST API."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

# Configure Rich logging early so all modules get proper handlers
from glyx_mcp.logging import configure_logging, get_logger

configure_logging()

import glyx_python_sdk
import logfire
import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from glyx_python_sdk.settings import settings

from api.webhooks import create_github_webhook_router, create_linear_webhook_router
from api.local_executor import start_local_executor, stop_local_executor
from supabase import create_client

# Configure Logfire early, before any instrumentation
logfire.configure(
    send_to_logfire="if-token-present",
    service_name="glyx-ai",
    token=os.environ.get("LOGFIRE_TOKEN"),
    environment=os.environ.get("ENVIRONMENT", "development"),
)
logfire.instrument_pydantic_ai()
logfire.instrument_httpx(capture_all=True)

_mcp_server_path = Path(__file__).parent.parent / "glyx_mcp" / "server.py"
_spec = importlib.util.spec_from_file_location("mcp_server_module", _mcp_server_path)
_mcp_server_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mcp_server_module)
mcp = _mcp_server_module.mcp

# Import API routes (after dynamic mcp module load)
from api.routes import (  # noqa: E402
    agent_tasks,
    agents,
    auth,
    cloud_instances,
    composable_workflows,
    deployments,
    devices,
    github,
    health,
    hitl,
    linear,
    memory,
    organizations,
    pair,
    root,
    sequences,
    streaming,
    tasks,
    workflows,
)

# Get agents directory from SDK package location
_sdk_path = Path(glyx_python_sdk.__file__).parent.parent
agents_dir = _sdk_path / "agents"


logger = get_logger(__name__)

# Create FastAPI app for REST API
api_app = FastAPI(
    title="Glyx AI API",
    description="""
# Glyx AI API

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

- [GitHub Repository](https://github.com/htelsiz/glyx-ai)
- [SDK Documentation](https://github.com/htelsiz/glyx-ai/blob/main/docs/SDK.md)
- [Deployment Guide](https://github.com/htelsiz/glyx-ai/blob/main/docs/DEPLOYMENT.md)
    """,
    version="0.2.0",
    contact={
        "name": "Glyx Team",
        "url": "https://github.com/htelsiz/glyx-ai",
        "email": "hakantelsiz@utexas.edu",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=[
        {"name": "Health", "description": "Health check and monitoring endpoints"},
        {"name": "Streaming", "description": "Real-time streaming endpoints for agent execution"},
        {"name": "Features", "description": "Feature pipeline management for multi-stage development workflows"},
        {"name": "Organizations", "description": "Organization management with Supabase backend"},
        {"name": "Tasks", "description": "Task creation and management, including AI-powered smart tasks"},
        {"name": "Authentication", "description": "User authentication via Supabase Auth"},
        {"name": "Memory", "description": "Project memory management with semantic search (Mem0)"},
        {"name": "Agents", "description": "Agent execution and management"},
        {"name": "GitHub", "description": "GitHub integration and repository management"},
        {"name": "Linear", "description": "Linear integration for issue tracking"},
    ],
)

logfire.instrument_fastapi(api_app)


# Mount static files
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    api_app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Get agents directory from SDK package location (same as MCP server)
_sdk_path = Path(glyx_python_sdk.__file__).parent.parent
agents_dir = _sdk_path / "agents"

# Register API routes
api_app.include_router(root.router)
api_app.include_router(health.router)
api_app.include_router(streaming.router)
api_app.include_router(sequences.router)
api_app.include_router(workflows.router)
api_app.include_router(composable_workflows.router)
api_app.include_router(organizations.router)
api_app.include_router(tasks.router)
api_app.include_router(agent_tasks.router)
api_app.include_router(hitl.router)
api_app.include_router(auth.router)
api_app.include_router(memory.router)
api_app.include_router(agents.router)
api_app.include_router(deployments.router)
api_app.include_router(github.router)
api_app.include_router(linear.router)
api_app.include_router(pair.router)
api_app.include_router(devices.router)
api_app.include_router(cloud_instances.router)

# Register webhook routers
github_webhook_router = create_github_webhook_router(
    lambda: create_client(settings.supabase_url, settings.supabase_anon_key)
)
linear_webhook_router = create_linear_webhook_router(
    lambda: create_client(settings.supabase_url, settings.supabase_anon_key)
)

api_app.include_router(github_webhook_router)
api_app.include_router(linear_webhook_router)

# Set agents_dir for health metrics
health.set_agents_dir(agents_dir)


# Create MCP ASGI app (path="/" means MCP handles root, we mount at /mcp)
mcp_app = mcp.http_app(path="/")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Custom lifespan that wraps MCP lifespan and starts local executor."""
    async with mcp_app.lifespan(app):
        # Start local agent executor (if device_id is configured)
        await start_local_executor()
        try:
            yield
        finally:
            await stop_local_executor()


# Create combined FastAPI app with custom lifespan
combined_app = FastAPI(
    title="Glyx AI - MCP + REST API",
    description=api_app.description,
    version=api_app.version,
    contact=api_app.contact,
    license_info=api_app.license_info,
    openapi_tags=api_app.openapi_tags,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware (must be before mounting)
combined_app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://glyx.ai",
        "https://www.glyx.ai",
    ],
    allow_origin_regex=r"^(chrome-extension://.*|https://.*\.glyx\.ai)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Mcp-Session-Id"],  # Required for Streamable HTTP
)

# Debug middleware to log MCP requests
@combined_app.middleware("http")
async def log_mcp_requests(request: Request, call_next):
    if request.url.path.startswith("/mcp"):
        auth_header = request.headers.get("Authorization", "NONE")
        accept_header = request.headers.get("Accept", "NONE")
        session_id = request.headers.get("Mcp-Session-Id", "NONE")
        logger.info(f"[MCP DEBUG] {request.method} {request.url.path}")
        logger.info(f"[MCP DEBUG]   Auth: {auth_header[:50] if auth_header != 'NONE' else 'NONE'}...")
        logger.info(f"[MCP DEBUG]   Accept: {accept_header}")
        logger.info(f"[MCP DEBUG]   Session-Id: {session_id}")
    response = await call_next(request)
    if request.url.path.startswith("/mcp"):
        logger.info(f"[MCP DEBUG]   Response: {response.status_code}")
    return response

# Mount MCP server at /mcp
combined_app.mount("/mcp", mcp_app)

# Include all API routers (preserves prefixes correctly)
combined_app.include_router(root.router)
combined_app.include_router(health.router)
combined_app.include_router(streaming.router)
combined_app.include_router(sequences.router)
combined_app.include_router(workflows.router)
combined_app.include_router(composable_workflows.router)
combined_app.include_router(organizations.router)
combined_app.include_router(tasks.router)
combined_app.include_router(agent_tasks.router)
combined_app.include_router(hitl.router)
combined_app.include_router(auth.router)
combined_app.include_router(memory.router)
combined_app.include_router(agents.router)
combined_app.include_router(deployments.router)
combined_app.include_router(github.router)
combined_app.include_router(linear.router)
combined_app.include_router(pair.router)
combined_app.include_router(devices.router)
combined_app.include_router(cloud_instances.router)
combined_app.include_router(github_webhook_router)
combined_app.include_router(linear_webhook_router)

# Mount static files on combined app
if static_path.exists():
    combined_app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

logfire.instrument_fastapi(combined_app)


# Exception handlers
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


async def main_http() -> None:
    """Run HTTP server with both MCP protocol and REST API."""
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting combined MCP + API server on http://0.0.0.0:{port}")

    config = uvicorn.Config(combined_app, host="0.0.0.0", port=port, log_level="debug")
    server = uvicorn.Server(config)
    await server.serve()


def run_http() -> None:
    """Entry point for HTTP server command."""
    asyncio.run(main_http())


def run_dev() -> None:
    """Entry point for local development with hot reload."""
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting dev server on http://0.0.0.0:{port} (reload enabled)")
    uvicorn.run(
        "api.server:combined_app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    asyncio.run(main_http())

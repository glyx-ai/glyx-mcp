"""Health check and monitoring endpoints."""

from __future__ import annotations

from datetime import datetime
from time import time
from typing import Any

from fastapi import APIRouter

from glyx_python_sdk import settings
from pathlib import Path

from api.utils import get_supabase

# Track server start time for uptime metrics
start_time = time()

# Global reference to agents_dir (set by server)
agents_dir: Path | None = None


def set_agents_dir(path: Path) -> None:
    """Set the agents directory path."""
    global agents_dir
    agents_dir = path


router = APIRouter(prefix="/api", tags=["Health"])


@router.get("/healthz", summary="Basic Health Check", response_description="Service health status")
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
        "service": "glyx-ai"
    }
    ```
    """
    return {"status": "ok", "timestamp": datetime.now().isoformat(), "service": "glyx-ai"}


@router.get(
    "/health/detailed",
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
        "service": "glyx-ai",
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
        "service": "glyx-ai",
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

    # Check Langfuse connection (if configured)
    langfuse = None
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        try:
            from langfuse import Langfuse

            langfuse = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            langfuse.auth_check()
            checks["checks"]["langfuse"] = {"status": "ok", "message": "Connected"}
        except Exception as e:
            checks["checks"]["langfuse"] = {"status": "error", "message": str(e)}
            checks["status"] = "degraded"
    else:
        checks["checks"]["langfuse"] = {"status": "not_configured"}

    # Check API keys
    checks["checks"]["openai"] = {"status": "configured" if settings.openai_api_key else "not_configured"}
    checks["checks"]["anthropic"] = {"status": "configured" if settings.anthropic_api_key else "not_configured"}
    checks["checks"]["openrouter"] = {"status": "configured" if settings.openrouter_api_key else "not_configured"}

    return checks


@router.get("/metrics", summary="Service Metrics", response_description="Prometheus-compatible metrics")
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
        "service": "glyx-ai",
        "uptime_seconds": 3600.5,
        "agents_available": 8
    }
    ```
    """
    agents_count = 0
    if agents_dir and agents_dir.exists():
        agents_count = len(list(agents_dir.glob("*.json")))

    return {
        "timestamp": datetime.now().isoformat(),
        "service": "glyx-ai",
        "uptime_seconds": time() - start_time,
        "agents_available": agents_count,
    }

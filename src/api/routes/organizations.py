"""Orchestration management API routes."""

from __future__ import annotations

from fastapi import APIRouter
from supabase import create_client

from glyx_python_sdk.settings import settings
from glyx_python_sdk.types import OrchestrationCreate, OrchestrationResponse

router = APIRouter(prefix="/api/orchestrations", tags=["Orchestrations"])

DEFAULT_PROJECT_ID = "a0000000-0000-0000-0000-000000000001"


@router.get("")
async def api_list_orchestrations() -> list[OrchestrationResponse]:
    """List all orchestrations from Supabase."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    response = (
        client.table("orchestrations")
        .select("*")
        .eq("project_id", DEFAULT_PROJECT_ID)
        .order("created_at", desc=True)  # type: ignore
        .execute()
    )
    return [OrchestrationResponse(**{**row, "id": str(row["id"])}) for row in response.data]


@router.post("")
async def api_create_orchestration(body: OrchestrationCreate) -> OrchestrationResponse:
    """Create a new orchestration in Supabase."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    data = {
        "project_id": DEFAULT_PROJECT_ID,
        "name": body.name,
        "description": body.description,
        "template": body.template,
        "config": body.config,
        "status": "draft",
        "stages": [],
    }
    response = client.table("orchestrations").insert(data).execute()
    row = response.data[0]
    return OrchestrationResponse(**{**row, "id": str(row["id"])})


@router.get("/{orchestration_id}")
async def api_get_orchestration(orchestration_id: str) -> OrchestrationResponse:
    """Get an orchestration by ID."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    response = client.table("orchestrations").select("*").eq("id", orchestration_id).single().execute()
    row = response.data
    return OrchestrationResponse(**{**row, "id": str(row["id"])})


@router.delete("/{orchestration_id}")
async def api_delete_orchestration(orchestration_id: str) -> dict[str, str]:
    """Delete an orchestration."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.table("orchestrations").delete().eq("id", orchestration_id).execute()
    return {"status": "deleted"}

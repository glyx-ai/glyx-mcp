"""Organization management API routes."""

from __future__ import annotations

from fastapi import APIRouter
from supabase import create_client

from glyx_python_sdk.settings import settings
from glyx_python_sdk.types import OrganizationCreate, OrganizationResponse

router = APIRouter(prefix="/api/organizations", tags=["Organizations"])

DEFAULT_PROJECT_ID = "a0000000-0000-0000-0000-000000000001"


@router.get("")
async def api_list_organizations() -> list[OrganizationResponse]:
    """List all organizations from Supabase."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    response = (
        client.table("organizations")
        .select("*")
        .eq("project_id", DEFAULT_PROJECT_ID)
        .order("created_at", desc=True)  # type: ignore
        .execute()
    )
    return [OrganizationResponse(**{**row, "id": str(row["id"])}) for row in response.data]


@router.post("")
async def api_create_organization(body: OrganizationCreate) -> OrganizationResponse:
    """Create a new organization in Supabase."""
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
    response = client.table("organizations").insert(data).execute()
    row = response.data[0]
    return OrganizationResponse(**{**row, "id": str(row["id"])})


@router.get("/{org_id}")
async def api_get_organization(org_id: str) -> OrganizationResponse:
    """Get an organization by ID."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    response = client.table("organizations").select("*").eq("id", org_id).single().execute()
    row = response.data
    return OrganizationResponse(**{**row, "id": str(row["id"])})


@router.delete("/{org_id}")
async def api_delete_organization(org_id: str) -> dict[str, str]:
    """Delete an organization."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.table("organizations").delete().eq("id", org_id).execute()
    return {"status": "deleted"}

"""Cloud instance provisioning API routes.

Each user can provision a personal Cloud Run MCP server.
The instance is tracked in the `cloud_instances` Supabase table.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import StrEnum

from fastapi import APIRouter, Header, HTTPException
from glyx_python_sdk.settings import settings
from pydantic import BaseModel
from supabase import create_client

from api.services.cloud_deployer import deploy, teardown
from api.session import validate_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cloud-instances", tags=["Cloud Instances"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class InstanceStatus(StrEnum):
    PROVISIONING = "provisioning"
    READY = "ready"
    ERROR = "error"
    DELETED = "deleted"


class CloudInstanceResponse(BaseModel):
    id: str
    user_id: str
    service_name: str
    endpoint: str | None = None
    status: str
    created_at: str
    updated_at: str


class ProvisionResponse(BaseModel):
    status: str
    instance: CloudInstanceResponse


class TeardownResponse(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_supabase():
    """Service-role client to bypass RLS for cloud instance operations."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _extract_user_id(authorization: str | None) -> str:
    """Extract and validate user_id from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    result = validate_access_token(authorization[7:])
    if not result:
        raise HTTPException(status_code=401, detail="Invalid token")
    return result[0]  # user_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    summary="Provision Cloud Instance",
    response_model=ProvisionResponse,
)
async def provision_instance(authorization: str | None = Header(None)) -> ProvisionResponse:
    """Provision a personal cloud MCP server for the current user.

    Creates a Cloud Run service with the user's ID baked in as OWNER_USER_ID.
    Only one instance per user is allowed.
    """
    user_id = _extract_user_id(authorization)
    supabase = _get_supabase()
    now = datetime.now(UTC).isoformat()

    # Check if user already has an instance
    existing = (
        supabase.table("cloud_instances")
        .select("*")
        .eq("user_id", user_id)
        .neq("status", InstanceStatus.DELETED)
        .execute()
    )
    if existing.data:
        row = existing.data[0]
        return ProvisionResponse(
            status="already_exists",
            instance=CloudInstanceResponse(**row),
        )

    # Insert row in provisioning state
    row = supabase.table("cloud_instances").insert({
        "user_id": user_id,
        "service_name": f"glyx-user-{user_id[:8]}",
        "status": InstanceStatus.PROVISIONING,
        "created_at": now,
        "updated_at": now,
    }).execute()

    instance_id = row.data[0]["id"]

    # Deploy Cloud Run service
    try:
        service_name, endpoint = await deploy(user_id)

        updated = supabase.table("cloud_instances").update({
            "service_name": service_name,
            "endpoint": endpoint,
            "status": InstanceStatus.READY,
            "updated_at": datetime.now(UTC).isoformat(),
        }).eq("id", instance_id).execute()

        return ProvisionResponse(
            status="provisioned",
            instance=CloudInstanceResponse(**updated.data[0]),
        )

    except Exception as e:
        logger.error(f"[CLOUD] Failed to provision for user {user_id[:8]}: {e}")
        supabase.table("cloud_instances").update({
            "status": InstanceStatus.ERROR,
            "updated_at": datetime.now(UTC).isoformat(),
        }).eq("id", instance_id).execute()
        raise HTTPException(status_code=500, detail=f"Provisioning failed: {e}") from e


@router.get(
    "/me",
    summary="Get My Cloud Instance",
    response_model=CloudInstanceResponse | None,
)
async def get_my_instance(authorization: str | None = Header(None)) -> CloudInstanceResponse | None:
    """Get the current user's cloud instance, if any."""
    user_id = _extract_user_id(authorization)
    supabase = _get_supabase()

    result = (
        supabase.table("cloud_instances")
        .select("*")
        .eq("user_id", user_id)
        .neq("status", InstanceStatus.DELETED)
        .execute()
    )

    if not result.data:
        return None

    return CloudInstanceResponse(**result.data[0])


@router.delete(
    "/me",
    summary="Tear Down Cloud Instance",
    response_model=TeardownResponse,
)
async def teardown_instance(authorization: str | None = Header(None)) -> TeardownResponse:
    """Delete the current user's cloud MCP server and Cloud Run service."""
    user_id = _extract_user_id(authorization)
    supabase = _get_supabase()

    result = (
        supabase.table("cloud_instances")
        .select("*")
        .eq("user_id", user_id)
        .neq("status", InstanceStatus.DELETED)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="No cloud instance found")

    # Tear down Cloud Run service
    try:
        await teardown(user_id)
    except Exception as e:
        logger.warning(f"[CLOUD] Teardown warning for user {user_id[:8]}: {e}")

    # Hard-delete row (unique constraint on user_id requires actual deletion)
    supabase.table("cloud_instances").delete().eq("id", result.data[0]["id"]).execute()

    return TeardownResponse(status="deleted")

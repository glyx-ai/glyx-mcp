"""Deployment management API routes."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException

from api.utils import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/deployments", tags=["Deployments"])


@router.get("")
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

        response = query.order("created_at", desc=True).execute()  # type: ignore
        return response.data
    except Exception as e:
        logger.error(f"Failed to list deployments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{deployment_id}")
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


@router.patch("/{deployment_id}")
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


@router.delete("/{deployment_id}")
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

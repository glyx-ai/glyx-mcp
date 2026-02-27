"""Device management and heartbeat endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client

from glyx_python_sdk.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/devices", tags=["Devices"])


class HeartbeatRequest(BaseModel):
    """Request body for device heartbeat."""

    uptime_seconds: float | None = None
    version: str | None = None
    hostname: str | None = None


class HeartbeatResponse(BaseModel):
    """Response for device heartbeat."""

    status: str
    device_id: str
    last_seen: str


@router.post(
    "/{device_id}/heartbeat",
    summary="Device Heartbeat",
    response_model=HeartbeatResponse,
    response_description="Heartbeat acknowledged with updated timestamp",
)
async def heartbeat(device_id: str, body: HeartbeatRequest | None = None) -> HeartbeatResponse:
    """
    Report that a device MCP executor is alive and running.

    Called periodically by the executor to indicate it's online and ready
    to accept tasks. Updates the `last_seen` timestamp in the database.

    **Path Parameters:**
    - `device_id`: UUID of the paired device

    **Request Body (optional):**
    - `uptime_seconds`: How long the executor has been running
    - `version`: Executor version string
    - `hostname`: Machine hostname (for verification)

    **Returns:**
    - `status`: "ok" on success
    - `device_id`: The device ID that was updated
    - `last_seen`: ISO timestamp of this heartbeat

    **Errors:**
    - 404: Device not found
    - 500: Database error
    """
    # Use service role key to bypass RLS - executor heartbeats are unauthenticated
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    now = datetime.now(UTC).isoformat()

    try:
        # Update last_seen timestamp
        update_data: dict[str, Any] = {"last_seen": now}

        # Optionally update hostname if provided
        if body and body.hostname:
            update_data["hostname"] = body.hostname

        result = (
            supabase.table("paired_devices")
            .update(update_data)
            .eq("id", device_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Device not found")

        logger.debug(f"Heartbeat received from device {device_id}")

        return HeartbeatResponse(
            status="ok",
            device_id=device_id,
            last_seen=now,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Heartbeat failed for device {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get(
    "/{device_id}/status",
    summary="Get Device Status",
    response_description="Device status including online/offline state",
)
async def get_device_status(device_id: str) -> dict[str, Any]:
    """
    Get the current status of a paired device.

    **Returns:**
    - `device_id`: Device UUID
    - `name`: Device display name
    - `status`: Device status (active, offline, etc.)
    - `last_seen`: ISO timestamp of last heartbeat (null if never seen)
    - `is_online`: Boolean indicating if device is online (heartbeat within 2 minutes)
    - `hostname`: Machine hostname

    **Errors:**
    - 404: Device not found
    """
    # Use service role key to bypass RLS for status checks
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    try:
        result = (
            supabase.table("paired_devices")
            .select("id, name, status, last_seen, hostname")
            .eq("id", device_id)
            .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Device not found")

        device = result.data
        last_seen = device.get("last_seen")

        # Calculate online status (heartbeat within last 2 minutes)
        is_online = False
        if last_seen:
            try:
                last_seen_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                age_seconds = (datetime.now(UTC) - last_seen_dt).total_seconds()
                is_online = age_seconds < 120  # 2 minutes
            except ValueError:
                pass

        return {
            "device_id": device["id"],
            "name": device.get("name"),
            "status": device.get("status"),
            "last_seen": last_seen,
            "is_online": is_online,
            "hostname": device.get("hostname"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get device status for {device_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e

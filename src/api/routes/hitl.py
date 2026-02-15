"""HITL (Human-in-the-Loop) request management API routes.

These endpoints handle the hitl_requests table for iOS orchestration.
Daemons create HITL requests when agents need human input.
Users respond via the iOS app.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import StrEnum

from fastapi import APIRouter, HTTPException
from glyx_python_sdk.settings import settings
from knockapi import Knock
from pydantic import BaseModel, Field

from supabase import create_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hitl", tags=["HITL"])


def _send_hitl_notification(
    user_id: str,
    hitl_request_id: str,
    task_id: str,
    prompt: str,
    agent_type: str = "agent",
    device_name: str | None = None,
) -> None:
    """Send HITL notification via Knock when agent needs user input.

    This triggers the 'agent-needs-input' workflow with the hitl_request_id
    included for deep linking directly to the HITL request.
    """
    api_key = settings.knock_api_key
    if not api_key:
        logger.debug("[KNOCK] No API key configured, skipping HITL notification")
        return

    knock = Knock(api_key=api_key)
    payload = {
        "event_type": "needs_input",
        "agent_type": agent_type,
        "session_id": task_id,
        "task_summary": prompt[:200],
        "urgency": "critical",
        "action_required": True,
        "hitl_request_id": hitl_request_id,
    }
    if device_name:
        payload["device_name"] = device_name

    try:
        knock.workflows.trigger(
            key="agent-needs-input",
            recipients=[user_id],
            data=payload,
        )
        logger.info(
            f"[KNOCK] Triggered agent-needs-input for user {user_id}, "
            f"hitl_request_id={hitl_request_id}"
        )
    except Exception as e:
        logger.warning(f"[KNOCK] Failed to send HITL notification: {e}")


class HITLStatus(StrEnum):
    """Valid HITL request status values."""

    PENDING = "pending"
    RESPONDED = "responded"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


# HITL expiration configuration: 5 minutes (matches table default)
HITL_EXPIRATION_MINUTES = 5


class CreateHITLRequest(BaseModel):
    """Request body for creating a HITL request."""

    task_id: str = Field(
        description="The agent task ID that is requesting human input",
    )
    prompt: str = Field(
        description="The question or prompt to show the user",
    )
    options: list[str] | None = Field(
        default=None,
        description="Optional predefined choices (e.g., ['Yes', 'No', 'Cancel'])",
    )


class HITLRequestResponse(BaseModel):
    """Response containing HITL request details."""

    id: str
    task_id: str
    user_id: str
    prompt: str
    options: list[str] | None = None
    response: str | None = None
    status: str
    created_at: str
    responded_at: str | None = None
    expires_at: str


class RespondToHITLRequest(BaseModel):
    """Request body for responding to a HITL request."""

    response: str = Field(
        description="The user's response to the HITL prompt",
    )


def _get_supabase():
    """Get Supabase client with service role key for backend operations."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@router.post(
    "",
    summary="Create HITL Request",
    description="""
Create a new HITL (Human-in-the-Loop) request.

This endpoint is called by the daemon when an agent needs human input to proceed.
The request is stored in the database and the user is notified via push notification.

**Task Status Update**: The associated agent_task status is automatically set to 'needs_input'.

**Push Notification**: A Knock notification is sent to the user with the hitl_request_id
for deep linking directly to the pending request.

**Expiration**: HITL requests expire after 5 minutes by default.
    """,
    response_model=HITLRequestResponse,
)
async def create_hitl_request(body: CreateHITLRequest) -> HITLRequestResponse:
    """Create a new HITL request for human input."""
    supabase = _get_supabase()

    # Fetch the task to get user_id, agent_type, device_id
    task_result = (
        supabase.table("agent_tasks")
        .select("id, user_id, status, agent_type, device_id")
        .eq("id", body.task_id)
        .maybe_single()
        .execute()
    )

    if not task_result.data:
        raise HTTPException(status_code=404, detail="Task not found")

    task = task_result.data
    user_id = task["user_id"]
    agent_type = task.get("agent_type", "agent")
    device_id = task.get("device_id")

    # Create the HITL request
    hitl_data = {
        "task_id": body.task_id,
        "user_id": user_id,
        "prompt": body.prompt,
        "options": body.options,
        "status": HITLStatus.PENDING.value,
    }

    result = supabase.table("hitl_requests").insert(hitl_data).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create HITL request")

    hitl_request = result.data[0]

    # Update the task status to needs_input
    supabase.table("agent_tasks").update({
        "status": "needs_input",
        "updated_at": datetime.now(UTC).isoformat(),
    }).eq("id", body.task_id).execute()

    # Send push notification via Knock with hitl_request_id for deep linking
    _send_hitl_notification(
        user_id=user_id,
        hitl_request_id=hitl_request["id"],
        task_id=body.task_id,
        prompt=body.prompt,
        agent_type=agent_type,
        device_name=device_id,
    )

    return HITLRequestResponse(
        id=hitl_request["id"],
        task_id=hitl_request["task_id"],
        user_id=hitl_request["user_id"],
        prompt=hitl_request["prompt"],
        options=hitl_request.get("options"),
        response=hitl_request.get("response"),
        status=hitl_request["status"],
        created_at=hitl_request["created_at"],
        responded_at=hitl_request.get("responded_at"),
        expires_at=hitl_request["expires_at"],
    )


@router.get(
    "/pending",
    summary="List Pending HITL Requests",
    description="""
List all pending HITL requests for a user.

Returns requests that are:
- Status = 'pending'
- Not expired (expires_at > now)

Ordered by creation time (oldest first) so users address requests in order.
    """,
    response_model=list[HITLRequestResponse],
)
async def list_pending_hitl_requests(user_id: str) -> list[HITLRequestResponse]:
    """List pending HITL requests for a user."""
    supabase = _get_supabase()

    # Query pending, non-expired requests
    result = (
        supabase.table("hitl_requests")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", HITLStatus.PENDING.value)
        .gt("expires_at", datetime.now(UTC).isoformat())
        .order("created_at", desc=False)
        .execute()
    )

    requests = result.data if result.data else []

    return [
        HITLRequestResponse(
            id=req["id"],
            task_id=req["task_id"],
            user_id=req["user_id"],
            prompt=req["prompt"],
            options=req.get("options"),
            response=req.get("response"),
            status=req["status"],
            created_at=req["created_at"],
            responded_at=req.get("responded_at"),
            expires_at=req["expires_at"],
        )
        for req in requests
    ]


@router.get(
    "/{hitl_id}",
    summary="Get HITL Request",
    description="Get details of a specific HITL request.",
    response_model=HITLRequestResponse,
)
async def get_hitl_request(hitl_id: str) -> HITLRequestResponse:
    """Get a HITL request by ID."""
    supabase = _get_supabase()

    result = (
        supabase.table("hitl_requests")
        .select("*")
        .eq("id", hitl_id)
        .maybe_single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="HITL request not found")

    req = result.data

    return HITLRequestResponse(
        id=req["id"],
        task_id=req["task_id"],
        user_id=req["user_id"],
        prompt=req["prompt"],
        options=req.get("options"),
        response=req.get("response"),
        status=req["status"],
        created_at=req["created_at"],
        responded_at=req.get("responded_at"),
        expires_at=req["expires_at"],
    )


class HITLExpirationCheckResponse(BaseModel):
    """Response from HITL expiration check endpoint."""

    expired_count: int
    hitl_ids: list[str]
    task_ids: list[str]


@router.post(
    "/expiration-check",
    summary="Check and Mark Expired HITL Requests",
    description="""
Mark stale HITL requests as expired and fail their associated tasks.

HITL requests are considered expired if:
- Status is 'pending'
- expires_at timestamp has passed

When a HITL request expires:
1. The HITL request status is set to 'expired'
2. The associated task status is set to 'failed'
3. The task error is set to indicate expiration

This ensures agents don't block indefinitely waiting for user input.
Call this endpoint periodically (e.g., every minute) via cron or iOS app.

Returns the count and IDs of HITL requests and tasks that were expired.
    """,
    response_model=HITLExpirationCheckResponse,
)
async def check_hitl_expirations() -> HITLExpirationCheckResponse:
    """Check for expired HITL requests and fail their tasks."""
    supabase = _get_supabase()

    now_iso = datetime.now(UTC).isoformat()

    # Find expired HITL requests: pending with expires_at < now
    expired_query = (
        supabase.table("hitl_requests")
        .select("id, task_id, user_id, prompt")
        .eq("status", HITLStatus.PENDING.value)
        .lt("expires_at", now_iso)
    )

    expired_result = expired_query.execute()
    expired_requests = expired_result.data if expired_result.data else []

    if not expired_requests:
        return HITLExpirationCheckResponse(
            expired_count=0,
            hitl_ids=[],
            task_ids=[],
        )

    # Mark each expired HITL request and fail its task
    expired_hitl_ids: list[str] = []
    expired_task_ids: list[str] = []

    for hitl in expired_requests:
        hitl_id = hitl["id"]
        task_id = hitl["task_id"]
        prompt = hitl.get("prompt", "")[:100]  # Truncate for error message

        # Mark HITL request as expired
        supabase.table("hitl_requests").update({
            "status": HITLStatus.EXPIRED.value,
        }).eq("id", hitl_id).execute()

        # Fail the associated task with expiration error
        error_msg = (
            f"HITL request expired: User did not respond within "
            f"{HITL_EXPIRATION_MINUTES} minutes. Prompt: {prompt}..."
        )
        supabase.table("agent_tasks").update({
            "status": "failed",
            "error": error_msg,
            "completed_at": now_iso,
            "updated_at": now_iso,
        }).eq("id", task_id).execute()

        expired_hitl_ids.append(hitl_id)
        expired_task_ids.append(task_id)

        logger.info(
            f"HITL request {hitl_id} expired, task {task_id} marked as failed"
        )

    return HITLExpirationCheckResponse(
        expired_count=len(expired_hitl_ids),
        hitl_ids=expired_hitl_ids,
        task_ids=expired_task_ids,
    )


@router.post(
    "/{hitl_id}/respond",
    summary="Respond to HITL Request",
    description="""
Submit a response to a HITL request.

This endpoint is called by the iOS app when a user responds to an agent's question.

**Validation**:
- Request must exist
- Request must be in 'pending' status
- Request must not be expired

**Side Effects**:
- HITL request status set to 'responded'
- responded_at timestamp set
- Associated task status set to 'running' (agent can continue)
    """,
    response_model=HITLRequestResponse,
)
async def respond_to_hitl_request(
    hitl_id: str,
    body: RespondToHITLRequest,
) -> HITLRequestResponse:
    """Submit a response to a HITL request."""
    supabase = _get_supabase()

    # Fetch the HITL request
    result = (
        supabase.table("hitl_requests")
        .select("*")
        .eq("id", hitl_id)
        .maybe_single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="HITL request not found")

    hitl_request = result.data

    # Validate status
    if hitl_request["status"] != HITLStatus.PENDING.value:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot respond to HITL request with status '{hitl_request['status']}'",
        )

    # Check expiration
    expires_at = datetime.fromisoformat(hitl_request["expires_at"].replace("Z", "+00:00"))
    if datetime.now(UTC) > expires_at:
        # Mark as expired and return error
        supabase.table("hitl_requests").update({
            "status": HITLStatus.EXPIRED.value,
        }).eq("id", hitl_id).execute()

        raise HTTPException(
            status_code=400,
            detail="HITL request has expired",
        )

    now = datetime.now(UTC).isoformat()

    # Update the HITL request with response
    update_result = (
        supabase.table("hitl_requests")
        .update({
            "response": body.response,
            "status": HITLStatus.RESPONDED.value,
            "responded_at": now,
        })
        .eq("id", hitl_id)
        .execute()
    )

    if not update_result.data:
        raise HTTPException(status_code=500, detail="Failed to update HITL request")

    updated_request = update_result.data[0]

    # Update the associated task status back to running
    supabase.table("agent_tasks").update({
        "status": "running",
        "updated_at": now,
    }).eq("id", hitl_request["task_id"]).execute()

    return HITLRequestResponse(
        id=updated_request["id"],
        task_id=updated_request["task_id"],
        user_id=updated_request["user_id"],
        prompt=updated_request["prompt"],
        options=updated_request.get("options"),
        response=updated_request.get("response"),
        status=updated_request["status"],
        created_at=updated_request["created_at"],
        responded_at=updated_request.get("responded_at"),
        expires_at=updated_request["expires_at"],
    )

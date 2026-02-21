"""Agent task management API routes.

These endpoints handle the agent_tasks table used for iOS orchestration.
The daemon on user devices calls these to update task status and stream output.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from fastapi import APIRouter, HTTPException
from glyx_python_sdk.settings import settings
from knockapi import Knock
from pydantic import BaseModel, Field

from supabase import create_client

logger = logging.getLogger(__name__)


def _send_agent_notification(
    user_id: str,
    task_id: str,
    workflow_key: str,
    agent_type: str = "agent",
    task_summary: str = "",
    device_name: str | None = None,
    error_message: str | None = None,
    execution_time_s: float | None = None,
) -> None:
    """Send agent lifecycle notification via Knock.

    Triggers one of: agent-start, agent-completed, agent-error
    """
    api_key = settings.knock_api_key
    if not api_key:
        logger.debug(f"[KNOCK] No API key configured, skipping {workflow_key} notification")
        return

    knock = Knock(api_key=api_key)

    # Map workflow key to event type
    event_type_map = {
        "agent-start": "started",
        "agent-completed": "completed",
        "agent-error": "error",
    }

    payload = {
        "event_type": event_type_map.get(workflow_key, workflow_key),
        "agent_type": agent_type,
        "session_id": task_id,  # For deep linking: glyx://agent/{session_id}
        "task_summary": task_summary[:200] if task_summary else "",
        "urgency": "high" if workflow_key == "agent-error" else "medium",
        "action_required": workflow_key == "agent-error",
    }

    if device_name:
        payload["device_name"] = device_name
    if error_message:
        payload["error_message"] = error_message[:500]
    if execution_time_s is not None:
        payload["execution_time_s"] = execution_time_s

    try:
        knock.workflows.trigger(
            key=workflow_key,
            recipients=[user_id],
            data=payload,
        )
        logger.info(f"[KNOCK] Triggered {workflow_key} for user {user_id}, task {task_id}")
    except Exception as e:
        logger.warning(f"[KNOCK] Failed to send {workflow_key} notification: {e}")

router = APIRouter(prefix="/api/agent-tasks", tags=["Agent Tasks"])


class TaskStatus(StrEnum):
    """Valid task status values."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_INPUT = "needs_input"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class TaskStatusUpdateRequest(BaseModel):
    """Request body for updating task status."""

    status: TaskStatus | None = Field(
        default=None,
        description="New task status",
    )
    output: str | None = Field(
        default=None,
        description="Output chunk to append (streaming)",
    )
    error: str | None = Field(
        default=None,
        description="Error message if task failed",
    )
    exit_code: int | None = Field(
        default=None,
        description="Exit code from agent process",
    )


class TaskStatusUpdateResponse(BaseModel):
    """Response after updating task status."""

    task_id: str
    status: str
    updated_at: str
    output_length: int | None = None


def _get_supabase():
    """Get Supabase client for backend operations.

    Uses sb_secret_ key which bypasses RLS.
    No authentication needed - the key itself grants full access.
    """
    if not settings.supabase_url or not settings.supabase_secret_key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_SECRET_KEY")

    return create_client(settings.supabase_url, settings.supabase_secret_key)


@router.post(
    "/{task_id}/status",
    summary="Update Task Status",
    description="""
Update the status and/or output of an agent task.

This endpoint is called by the daemon running on user devices to:
- Update task status (pending → running → completed/failed)
- Append output chunks as the agent produces output
- Report errors and exit codes

**Output Streaming**: The `output` field appends to existing output, enabling
real-time streaming. Each call adds to the previous output rather than replacing it.
    """,
    response_model=TaskStatusUpdateResponse,
)
async def update_task_status(
    task_id: str,
    body: TaskStatusUpdateRequest,
) -> TaskStatusUpdateResponse:
    """Update task status and optionally append output.

    Uses direct table access with sb_secret_ key (bypasses RLS).
    """
    logger.info(f"[{task_id}] Status update request: status={body.status}, output_len={len(body.output) if body.output else 0}")

    try:
        supabase = _get_supabase()
    except Exception as e:
        logger.error(f"[{task_id}] Failed to create Supabase client: {e}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {e}")

    # First, get the existing task to append output and get metadata for notifications
    try:
        existing = supabase.table("agent_tasks").select(
            "output, status, user_id, agent_type, device_id, payload, created_at"
        ).eq("id", task_id).single().execute()
    except Exception as e:
        logger.error(f"[{task_id}] Task not found: {e}")
        raise HTTPException(status_code=404, detail="Task not found")

    if not existing.data:
        raise HTTPException(status_code=404, detail="Task not found")

    existing_output = existing.data.get("output") or ""
    existing_status = existing.data.get("status")
    user_id = existing.data.get("user_id")
    agent_type = existing.data.get("agent_type", "agent")
    device_id = existing.data.get("device_id")
    payload = existing.data.get("payload") or {}
    task_summary = payload.get("prompt", "")[:200] if isinstance(payload, dict) else ""
    created_at = existing.data.get("created_at")
    now = datetime.now(UTC).isoformat()

    # Build update payload
    update_data: dict = {"updated_at": now}

    if body.status:
        update_data["status"] = body.status.value

        # Set started_at when transitioning to running
        if body.status == TaskStatus.RUNNING:
            update_data["started_at"] = now

        # Set completed_at for terminal states
        if body.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMEOUT):
            update_data["completed_at"] = now

    if body.output:
        update_data["output"] = existing_output + body.output

    if body.error:
        update_data["error"] = body.error

    if body.exit_code is not None:
        update_data["exit_code"] = body.exit_code

    # Update the task
    try:
        result = supabase.table("agent_tasks").update(update_data).eq("id", task_id).execute()
    except Exception as e:
        logger.error(f"[{task_id}] Failed to update task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update task: {e}")

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update task")

    updated_task = result.data[0]
    new_status = updated_task.get("status")
    logger.info(f"[{task_id}] Task updated successfully: status={new_status}")

    # Send push notifications for status transitions (only if user_id is available)
    if user_id and body.status and existing_status != body.status.value:
        # Calculate execution time for completed/failed tasks
        execution_time_s = None
        if created_at and body.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            try:
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                execution_time_s = (datetime.now(UTC) - created).total_seconds()
            except Exception:
                pass

        if body.status == TaskStatus.RUNNING:
            _send_agent_notification(
                user_id=user_id,
                task_id=task_id,
                workflow_key="agent-start",
                agent_type=agent_type,
                task_summary=task_summary,
                device_name=device_id,
            )
        elif body.status == TaskStatus.COMPLETED:
            _send_agent_notification(
                user_id=user_id,
                task_id=task_id,
                workflow_key="agent-completed",
                agent_type=agent_type,
                task_summary=task_summary,
                device_name=device_id,
                execution_time_s=execution_time_s,
            )
        elif body.status == TaskStatus.FAILED:
            _send_agent_notification(
                user_id=user_id,
                task_id=task_id,
                workflow_key="agent-error",
                agent_type=agent_type,
                task_summary=task_summary,
                device_name=device_id,
                error_message=body.error,
                execution_time_s=execution_time_s,
            )

    return TaskStatusUpdateResponse(
        task_id=task_id,
        status=new_status or "unknown",
        updated_at=updated_task.get("updated_at", now),
        output_length=len(updated_task.get("output") or ""),
    )


@router.get(
    "/{task_id}",
    summary="Get Task Details",
    description="Get full details of an agent task including output and status.",
)
async def get_task(task_id: str) -> dict:
    """Get task by ID using direct table access."""
    supabase = _get_supabase()

    try:
        result = supabase.table("agent_tasks").select("*").eq("id", task_id).single().execute()
    except Exception as e:
        logger.error(f"[{task_id}] Failed to get task: {e}")
        raise HTTPException(status_code=404, detail="Task not found")

    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")

    return result.data


@router.get(
    "",
    summary="List User Tasks",
    description="List agent tasks for a user, optionally filtered by device or status.",
)
async def list_tasks(
    user_id: str | None = None,
    device_id: str | None = None,
    status: TaskStatus | None = None,
    limit: int = 50,
) -> list[dict]:
    """List tasks using direct table access."""
    supabase = _get_supabase()

    columns = (
        "id, user_id, device_id, agent_type, task_type, "
        "status, created_at, updated_at, started_at, completed_at"
    )
    query = (
        supabase.table("agent_tasks")
        .select(columns)
        .order("created_at", desc=True)
        .limit(limit)
    )

    if user_id:
        query = query.eq("user_id", user_id)

    if device_id:
        query = query.eq("device_id", device_id)

    if status:
        query = query.eq("status", status.value)

    result = query.execute()

    return result.data if result.data else []


# Task timeout configuration: 10 minutes
TASK_TIMEOUT_MINUTES = 10


class TimeoutCheckResponse(BaseModel):
    """Response from timeout check endpoint."""

    timed_out_count: int
    task_ids: list[str]


class CancelTaskResponse(BaseModel):
    """Response from cancel task endpoint."""

    task_id: str
    status: str
    cancelled_at: str


@router.post(
    "/{task_id}/cancel",
    summary="Cancel a Running Task",
    description="""
Cancel a task that is currently pending or running.

Only tasks in 'pending' or 'running' status can be cancelled.
Already completed, failed, or cancelled tasks will return a 400 error.

Returns the updated task status.
    """,
    response_model=CancelTaskResponse,
)
async def cancel_task(task_id: str) -> CancelTaskResponse:
    """Cancel a running or pending task using direct table access."""
    supabase = _get_supabase()

    # Get current status
    try:
        existing = supabase.table("agent_tasks").select("status").eq("id", task_id).single().execute()
    except Exception as e:
        logger.error(f"[{task_id}] Task not found: {e}")
        raise HTTPException(status_code=404, detail="Task not found")

    if not existing.data:
        raise HTTPException(status_code=404, detail="Task not found")

    current_status = existing.data.get("status")

    # Only cancel pending or running tasks
    if current_status not in ("pending", "running"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel task in {current_status} status"
        )

    now = datetime.now(UTC).isoformat()

    # Update to cancelled
    try:
        result = supabase.table("agent_tasks").update({
            "status": "cancelled",
            "completed_at": now,
            "updated_at": now,
        }).eq("id", task_id).execute()
    except Exception as e:
        logger.error(f"[{task_id}] Failed to cancel task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel task: {e}")

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to cancel task")

    logger.info(f"Task {task_id} cancelled")

    return CancelTaskResponse(
        task_id=task_id,
        status=TaskStatus.CANCELLED.value,
        cancelled_at=now,
    )


class RetryTaskResponse(BaseModel):
    """Response from retry task endpoint."""

    original_task_id: str
    new_task_id: str
    status: str
    created_at: str


@router.post(
    "/{task_id}/retry",
    summary="Retry a Failed Task",
    description="""
Retry a task that has failed, timed out, or was cancelled.

Creates a new task with the same parameters (device_id, agent_type, payload)
as the original task. The original task remains unchanged.

Only tasks in 'failed', 'timeout', or 'cancelled' status can be retried.
    """,
    response_model=RetryTaskResponse,
)
async def retry_task(task_id: str) -> RetryTaskResponse:
    """Retry a failed, timed out, or cancelled task using direct table access."""
    supabase = _get_supabase()

    # Get original task
    try:
        result = supabase.table("agent_tasks").select("*").eq("id", task_id).single().execute()
    except Exception as e:
        logger.error(f"[{task_id}] Task not found: {e}")
        raise HTTPException(status_code=404, detail="Task not found")

    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")

    original_task = result.data
    current_status = original_task.get("status")

    # Only allow retrying failed/timeout/cancelled tasks
    if current_status not in ("failed", "timeout", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry task in {current_status} status"
        )

    now = datetime.now(UTC).isoformat()
    new_task_id = str(uuid.uuid4())

    # Create new task
    new_task_data = {
        "id": new_task_id,
        "user_id": original_task.get("user_id"),
        "device_id": original_task.get("device_id"),
        "agent_type": original_task.get("agent_type"),
        "task_type": original_task.get("task_type") or "prompt",
        "payload": original_task.get("payload"),
        "status": "pending",
        "created_at": now,
        "updated_at": now,
    }

    try:
        insert_result = supabase.table("agent_tasks").insert(new_task_data).execute()
    except Exception as e:
        logger.error(f"[{task_id}] Failed to create retry task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retry task: {e}")

    if not insert_result.data:
        raise HTTPException(status_code=500, detail="Failed to retry task")

    new_task = insert_result.data[0]

    logger.info(f"Task {task_id} retried as new task {new_task_id}")

    return RetryTaskResponse(
        original_task_id=task_id,
        new_task_id=new_task_id,
        status=TaskStatus.PENDING.value,
        created_at=new_task.get("created_at", now),
    )


@router.post(
    "/timeout-check",
    summary="Check and Mark Timed Out Tasks",
    description="""
Mark stale tasks as timed out.

Tasks are considered timed out if:
- Status is 'pending' or 'running'
- Last update (updated_at) was more than 10 minutes ago

This endpoint can be called periodically by a cron job or the iOS app
to ensure stuck tasks don't hang forever.

Returns the count and IDs of tasks that were marked as timed out.
    """,
    response_model=TimeoutCheckResponse,
)
async def check_timeouts() -> TimeoutCheckResponse:
    """Check for stale tasks and mark them as timed out using direct table access."""
    supabase = _get_supabase()

    now = datetime.now(UTC)
    cutoff = now - __import__("datetime").timedelta(minutes=TASK_TIMEOUT_MINUTES)
    cutoff_str = cutoff.isoformat()
    now_str = now.isoformat()

    # Find stale tasks
    try:
        stale_tasks = (
            supabase.table("agent_tasks")
            .select("id")
            .in_("status", ["pending", "running"])
            .lt("updated_at", cutoff_str)
            .execute()
        )
    except Exception as e:
        logger.error(f"Failed to find stale tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check timeouts: {e}")

    if not stale_tasks.data:
        return TimeoutCheckResponse(timed_out_count=0, task_ids=[])

    task_ids = [task["id"] for task in stale_tasks.data]

    # Update stale tasks to timeout status
    try:
        supabase.table("agent_tasks").update({
            "status": "timeout",
            "error": f"Task timed out after {TASK_TIMEOUT_MINUTES} minutes with no update",
            "completed_at": now_str,
            "updated_at": now_str,
        }).in_("id", task_ids).execute()
    except Exception as e:
        logger.error(f"Failed to mark tasks as timed out: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to mark timeouts: {e}")

    logger.info(f"Marked {len(task_ids)} tasks as timed out: {task_ids}")

    return TimeoutCheckResponse(
        timed_out_count=len(task_ids),
        task_ids=task_ids,
    )

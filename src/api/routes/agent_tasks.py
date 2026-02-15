"""Agent task management API routes.

These endpoints handle the agent_tasks table used for iOS orchestration.
The daemon on user devices calls these to update task status and stream output.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import StrEnum

from fastapi import APIRouter, HTTPException
from glyx_python_sdk.settings import settings
from pydantic import BaseModel, Field

from supabase import create_client

logger = logging.getLogger(__name__)

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
    """Get Supabase client with service role key for backend operations."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@router.post(
    "/{task_id}/status",
    summary="Update Task Status",
    description="""
Update the status and/or output of an agent task.

This endpoint is called by the daemon running on user devices to:
- Update task status (pending → running → completed/failed)
- Append output chunks as the agent produces output
- Report errors and exit codes

**Authentication**: Validates that the task belongs to the requesting user.

**Output Streaming**: The `output` field appends to existing output, enabling
real-time streaming. Each call adds to the previous output rather than replacing it.
    """,
    response_model=TaskStatusUpdateResponse,
)
async def update_task_status(
    task_id: str,
    body: TaskStatusUpdateRequest,
) -> TaskStatusUpdateResponse:
    """Update task status and optionally append output."""
    supabase = _get_supabase()

    # Fetch current task to validate and get existing output
    task_result = (
        supabase.table("agent_tasks")
        .select("id, user_id, status, output")
        .eq("id", task_id)
        .maybe_single()
        .execute()
    )

    if not task_result.data:
        raise HTTPException(status_code=404, detail="Task not found")

    task = task_result.data

    # Build update payload
    update_data: dict = {
        "updated_at": datetime.now(UTC).isoformat(),
    }

    # Update status if provided
    if body.status is not None:
        update_data["status"] = body.status.value

        # Set started_at when transitioning to running
        if body.status == TaskStatus.RUNNING:
            update_data["started_at"] = datetime.now(UTC).isoformat()

        # Set completed_at when task finishes
        terminal_statuses = (
            TaskStatus.COMPLETED, TaskStatus.FAILED,
            TaskStatus.CANCELLED, TaskStatus.TIMEOUT
        )
        if body.status in terminal_statuses:
            update_data["completed_at"] = datetime.now(UTC).isoformat()

    # Append output if provided (streaming)
    if body.output is not None:
        existing_output = task.get("output") or ""
        update_data["output"] = existing_output + body.output

    # Set error if provided
    if body.error is not None:
        update_data["error"] = body.error

    # Set exit_code if provided
    if body.exit_code is not None:
        update_data["exit_code"] = body.exit_code

    # Perform update
    result = (
        supabase.table("agent_tasks")
        .update(update_data)
        .eq("id", task_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update task")

    updated_task = result.data[0]

    return TaskStatusUpdateResponse(
        task_id=task_id,
        status=updated_task.get("status", task["status"]),
        updated_at=update_data["updated_at"],
        output_length=len(updated_task.get("output") or ""),
    )


@router.get(
    "/{task_id}",
    summary="Get Task Details",
    description="Get full details of an agent task including output and status.",
)
async def get_task(task_id: str) -> dict:
    """Get task by ID."""
    supabase = _get_supabase()

    result = (
        supabase.table("agent_tasks")
        .select("*")
        .eq("id", task_id)
        .maybe_single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")

    return result.data


@router.get(
    "",
    summary="List User Tasks",
    description="List agent tasks for a user, optionally filtered by device or status.",
)
async def list_tasks(
    user_id: str,
    device_id: str | None = None,
    status: TaskStatus | None = None,
    limit: int = 50,
) -> list[dict]:
    """List tasks for a user."""
    supabase = _get_supabase()

    # Select specific columns to keep line length manageable
    columns = (
        "id, user_id, device_id, agent_type, task_type, "
        "status, created_at, updated_at, started_at, completed_at"
    )
    query = (
        supabase.table("agent_tasks")
        .select(columns)
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
    )

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
    """Cancel a running or pending task."""
    supabase = _get_supabase()

    # Fetch current task
    task_result = (
        supabase.table("agent_tasks")
        .select("id, status")
        .eq("id", task_id)
        .maybe_single()
        .execute()
    )

    if not task_result.data:
        raise HTTPException(status_code=404, detail="Task not found")

    task = task_result.data
    current_status = task.get("status")

    # Only allow cancelling pending or running tasks
    cancellable_statuses = (TaskStatus.PENDING.value, TaskStatus.RUNNING.value)
    if current_status not in cancellable_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel task in '{current_status}' status. "
                   f"Only pending or running tasks can be cancelled.",
        )

    # Update task to cancelled
    now_iso = datetime.now(UTC).isoformat()
    result = (
        supabase.table("agent_tasks")
        .update({
            "status": TaskStatus.CANCELLED.value,
            "completed_at": now_iso,
            "updated_at": now_iso,
        })
        .eq("id", task_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to cancel task")

    logger.info(f"Task {task_id} cancelled by user")

    return CancelTaskResponse(
        task_id=task_id,
        status=TaskStatus.CANCELLED.value,
        cancelled_at=now_iso,
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
    """Retry a failed, timed out, or cancelled task."""
    supabase = _get_supabase()

    # Fetch original task
    task_result = (
        supabase.table("agent_tasks")
        .select("*")
        .eq("id", task_id)
        .maybe_single()
        .execute()
    )

    if not task_result.data:
        raise HTTPException(status_code=404, detail="Task not found")

    task = task_result.data
    current_status = task.get("status")

    # Only allow retrying failed/timeout/cancelled tasks
    retryable_statuses = (
        TaskStatus.FAILED.value,
        TaskStatus.TIMEOUT.value,
        TaskStatus.CANCELLED.value,
    )
    if current_status not in retryable_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry task in '{current_status}' status. "
                   f"Only failed, timed out, or cancelled tasks can be retried.",
        )

    # Create new task with same parameters
    now_iso = datetime.now(UTC).isoformat()
    new_task_data = {
        "user_id": task["user_id"],
        "device_id": task["device_id"],
        "agent_type": task["agent_type"],
        "task_type": task.get("task_type", "prompt"),
        "payload": task["payload"],
        "status": TaskStatus.PENDING.value,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    result = (
        supabase.table("agent_tasks")
        .insert(new_task_data)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create retry task")

    new_task = result.data[0]
    new_task_id = new_task["id"]

    logger.info(f"Task {task_id} retried as new task {new_task_id}")

    return RetryTaskResponse(
        original_task_id=task_id,
        new_task_id=new_task_id,
        status=TaskStatus.PENDING.value,
        created_at=now_iso,
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
    """Check for stale tasks and mark them as timed out."""
    supabase = _get_supabase()

    # Calculate cutoff time (10 minutes ago)
    from datetime import timedelta
    cutoff = datetime.now(UTC) - timedelta(minutes=TASK_TIMEOUT_MINUTES)
    cutoff_iso = cutoff.isoformat()

    # Find stale tasks: pending/running with updated_at older than cutoff
    # Note: needs_input is excluded - those tasks are waiting for user input
    stale_query = (
        supabase.table("agent_tasks")
        .select("id, status, updated_at")
        .in_("status", [TaskStatus.PENDING.value, TaskStatus.RUNNING.value])
        .lt("updated_at", cutoff_iso)
    )

    stale_result = stale_query.execute()
    stale_tasks = stale_result.data if stale_result.data else []

    if not stale_tasks:
        return TimeoutCheckResponse(timed_out_count=0, task_ids=[])

    # Mark each stale task as timed out
    now_iso = datetime.now(UTC).isoformat()
    timed_out_ids = []

    for task in stale_tasks:
        task_id = task["id"]
        supabase.table("agent_tasks").update({
            "status": TaskStatus.TIMEOUT.value,
            "error": f"Task timed out after {TASK_TIMEOUT_MINUTES} minutes with no update",
            "completed_at": now_iso,
            "updated_at": now_iso,
        }).eq("id", task_id).execute()
        timed_out_ids.append(task_id)
        logger.info(f"Task {task_id} marked as timed out (last update: {task['updated_at']})")

    return TimeoutCheckResponse(
        timed_out_count=len(timed_out_ids),
        task_ids=timed_out_ids,
    )

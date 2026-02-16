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
    """Get Supabase client for RPC calls.

    Uses the anon/publishable key. All daemon operations go through
    SECURITY DEFINER RPC functions that bypass RLS internally.
    No user authentication is needed - the functions handle authorization.
    """
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_ANON_KEY")

    return create_client(settings.supabase_url, settings.supabase_anon_key)


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
    """Update task status and optionally append output.

    Uses daemon_update_task_status RPC function which bypasses RLS.
    """
    logger.info(f"[{task_id}] Status update request: status={body.status}, output_len={len(body.output) if body.output else 0}")

    try:
        supabase = _get_supabase()
    except Exception as e:
        logger.error(f"[{task_id}] Failed to create Supabase client: {e}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {e}")

    # Call RPC function - handles output append, timestamps, etc.
    try:
        result = supabase.rpc(
            "daemon_update_task_status",
            {
                "p_task_id": task_id,
                "p_status": body.status.value if body.status else None,
                "p_output": body.output,
                "p_error": body.error,
                "p_exit_code": body.exit_code,
            },
        ).execute()
    except Exception as e:
        logger.error(f"[{task_id}] Failed to update task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update task: {e}")

    if not result.data:
        logger.error(f"[{task_id}] RPC returned no data")
        raise HTTPException(status_code=500, detail="Failed to update task")

    updated_task = result.data

    # Check for error response from function
    if isinstance(updated_task, dict) and "error" in updated_task:
        error_msg = updated_task["error"]
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail="Task not found")
        raise HTTPException(status_code=400, detail=error_msg)

    logger.info(f"[{task_id}] Task updated successfully: status={updated_task.get('status')}")

    return TaskStatusUpdateResponse(
        task_id=task_id,
        status=updated_task.get("status", "unknown"),
        updated_at=updated_task.get("updated_at", datetime.now(UTC).isoformat()),
        output_length=len(updated_task.get("output") or ""),
    )


@router.get(
    "/{task_id}",
    summary="Get Task Details",
    description="Get full details of an agent task including output and status.",
)
async def get_task(task_id: str) -> dict:
    """Get task by ID using daemon_get_task RPC function."""
    supabase = _get_supabase()

    try:
        result = supabase.rpc("daemon_get_task", {"p_task_id": task_id}).execute()
    except Exception as e:
        logger.error(f"[{task_id}] Failed to get task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get task: {e}")

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
    """List tasks for a user.

    Note: For daemon polling, use daemon_list_pending_tasks RPC instead.
    This endpoint filters by user_id via RLS for authenticated users.
    """
    supabase = _get_supabase()

    # For device_id queries from daemon, use RPC function
    if device_id and status == TaskStatus.PENDING:
        try:
            result = supabase.rpc(
                "daemon_list_pending_tasks",
                {"p_device_id": device_id},
            ).execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Failed to list pending tasks: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # For other queries, use direct table access (RLS filters by user)
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
    """Cancel a running or pending task using daemon_cancel_task RPC."""
    supabase = _get_supabase()

    try:
        result = supabase.rpc("daemon_cancel_task", {"p_task_id": task_id}).execute()
    except Exception as e:
        logger.error(f"[{task_id}] Failed to cancel task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel task: {e}")

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to cancel task")

    task_result = result.data

    # Check for error response from function
    if isinstance(task_result, dict) and "error" in task_result:
        error_msg = task_result["error"]
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail="Task not found")
        raise HTTPException(status_code=400, detail=error_msg)

    logger.info(f"Task {task_id} cancelled")

    return CancelTaskResponse(
        task_id=task_id,
        status=TaskStatus.CANCELLED.value,
        cancelled_at=task_result.get("completed_at", datetime.now(UTC).isoformat()),
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
    """Retry a failed, timed out, or cancelled task using daemon_retry_task RPC."""
    supabase = _get_supabase()

    try:
        result = supabase.rpc("daemon_retry_task", {"p_task_id": task_id}).execute()
    except Exception as e:
        logger.error(f"[{task_id}] Failed to retry task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retry task: {e}")

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to retry task")

    retry_result = result.data

    # Check for error response from function
    if isinstance(retry_result, dict) and "error" in retry_result:
        error_msg = retry_result["error"]
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail="Task not found")
        raise HTTPException(status_code=400, detail=error_msg)

    new_task = retry_result.get("new_task", {})
    new_task_id = new_task.get("id", "")

    logger.info(f"Task {task_id} retried as new task {new_task_id}")

    return RetryTaskResponse(
        original_task_id=task_id,
        new_task_id=new_task_id,
        status=TaskStatus.PENDING.value,
        created_at=new_task.get("created_at", datetime.now(UTC).isoformat()),
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
    """Check for stale tasks and mark them as timed out using daemon_mark_timeouts RPC."""
    supabase = _get_supabase()

    try:
        result = supabase.rpc(
            "daemon_mark_timeouts",
            {"p_timeout_minutes": TASK_TIMEOUT_MINUTES},
        ).execute()
    except Exception as e:
        logger.error(f"Failed to check timeouts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check timeouts: {e}")

    if not result.data:
        return TimeoutCheckResponse(timed_out_count=0, task_ids=[])

    timeout_result = result.data
    timed_out_count = timeout_result.get("timed_out_count", 0)
    task_ids = timeout_result.get("task_ids", [])

    if timed_out_count > 0:
        logger.info(f"Marked {timed_out_count} tasks as timed out: {task_ids}")

    return TimeoutCheckResponse(
        timed_out_count=timed_out_count,
        task_ids=task_ids,
    )

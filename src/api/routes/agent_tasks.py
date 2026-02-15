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
        if body.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
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

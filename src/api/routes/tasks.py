"""Task management API routes."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from fastapi import APIRouter, HTTPException

from api.utils import get_supabase
from glyx_python_sdk import settings
from glyx_python_sdk.types import SmartTaskRequest, TaskResponse
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])

SMART_TASK_SYSTEM_PROMPT = """You are a task creation assistant. Given selected text from a webpage, create a clear and actionable task.

Return a JSON object with:
- title: A concise task title (max 80 chars)
- description: A detailed description of what needs to be done

The task should be:
- Actionable and specific
- Based on the context provided
- Professional in tone

Return ONLY valid JSON, no markdown or explanation."""


def get_openrouter_client() -> AsyncOpenAI:
    """Get OpenRouter client."""
    api_key = settings.openrouter_api_key
    if not api_key:
        raise HTTPException(status_code=500, detail="OpenRouter API key not configured")
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


@router.get("")
async def api_list_tasks() -> list[TaskResponse]:
    """List all tasks from Supabase."""
    client = get_supabase()
    response = client.table("tasks").select("*").order("created_at", desc=True).execute()  # type: ignore
    return [TaskResponse(**{**row, "id": str(row["id"])}) for row in response.data]


@router.post("")
async def api_create_task(body: dict) -> TaskResponse:
    """Create a new task in Supabase."""
    client = get_supabase()
    insert_data = {
        "title": body["title"],
        "description": body["description"],
        "organization_id": body["organization_id"],
        "status": "in_progress",
        "assigned_at": datetime.now().isoformat(),
    }
    response = client.table("tasks").insert(insert_data).execute()
    row = response.data[0]
    return TaskResponse(**{**row, "id": str(row["id"])})


@router.get("/{task_id}")
async def api_get_task(task_id: str) -> TaskResponse:
    """Get a task by ID."""
    client = get_supabase()
    response = client.table("tasks").select("*").eq("id", task_id).single().execute()
    row = response.data
    return TaskResponse(**{**row, "id": str(row["id"])})


@router.get("/linear/{session_id}")
async def api_get_linear_task(session_id: str) -> TaskResponse | None:
    """Get a task by Linear session ID."""
    client = get_supabase()
    response = (
        client.table("tasks")
        .select("*")
        .eq("linear_session_id", session_id)
        .order("created_at", desc=True)  # type: ignore
        .limit(1)
        .execute()
    )
    if not response.data:
        return None
    row = response.data[0]
    return TaskResponse(**{**row, "id": str(row["id"])})


@router.get("/linear/workspace/{workspace_id}")
async def api_list_linear_tasks(workspace_id: str) -> list[TaskResponse]:
    """List all tasks for a Linear workspace."""
    client = get_supabase()
    response = (
        client.table("tasks")
        .select("*")
        .eq("linear_workspace_id", workspace_id)
        .order("created_at", desc=True)  # type: ignore
        .execute()
    )
    return [TaskResponse(**{**row, "id": str(row["id"])}) for row in response.data]


@router.patch("/{task_id}")
async def api_update_task(task_id: str, body: dict) -> TaskResponse:
    """Update a task."""
    client = get_supabase()
    update_data = {k: v for k, v in body.items() if v is not None}
    response = client.table("tasks").update(update_data).eq("id", task_id).execute()
    row = response.data[0]
    return TaskResponse(**{**row, "id": str(row["id"])})


@router.delete("/{task_id}")
async def api_delete_task(task_id: str) -> dict[str, str]:
    """Delete a task."""
    client = get_supabase()
    client.table("tasks").delete().eq("id", task_id).execute()
    return {"status": "deleted"}


@router.post(
    "/smart",
    summary="Create Smart Task",
    response_description="AI-generated task from selected text",
    status_code=201,
)
async def api_create_smart_task(body: SmartTaskRequest) -> TaskResponse:
    """
    Create a task using AI to generate title and description from selected text.

    Uses Claude Sonnet 4 via OpenRouter to analyze the selected text and create
    a well-structured, actionable task with appropriate title and description.

    **Request Body:**
    - `selected_text`: Text selected by user (required)
    - `page_title`: Title of the source page (optional)
    - `page_url`: URL of the source page (optional)

    **Example:**
    ```json
    {
        "selected_text": "Implement JWT authentication with refresh tokens",
        "page_title": "Security Best Practices",
        "page_url": "https://example.com/security"
    }
    ```

    **Response:** Task object with AI-generated title and description
    """
    if not body.selected_text.strip():
        raise HTTPException(status_code=400, detail="Selected text is required")

    # Build prompt with context
    user_prompt = f"""Create a task from this selected text:

Selected text: "{body.selected_text}"
{f"Page title: {body.page_title}" if body.page_title else ""}
{f"Source URL: {body.page_url}" if body.page_url else ""}

Return JSON with "title" and "description" fields."""

    # Call OpenRouter API
    openrouter = get_openrouter_client()
    try:
        response = await openrouter.chat.completions.create(
            model="anthropic/claude-sonnet-4",
            messages=[
                {"role": "system", "content": SMART_TASK_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=500,
        )
        ai_text = response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"OpenRouter API error: {e}")
        raise HTTPException(status_code=500, detail=f"AI generation failed: {e}")

    # Parse AI response
    try:
        cleaned = re.sub(r"```json\n?|\n?```", "", ai_text).strip()
        task_data = json.loads(cleaned)
        title = task_data.get("title", body.selected_text[:80])
        description = task_data.get("description", body.selected_text)
    except (json.JSONDecodeError, KeyError):
        # Fallback if AI returns malformed JSON
        title = body.selected_text[:80]
        description = f'Task created from: "{body.selected_text}"'

    # Add source URL to description
    full_description = f"{description}\n\nSource: {body.page_url}" if body.page_url else description

    # Create task in Supabase
    supabase = get_supabase()
    insert_data = {
        "title": title,
        "description": full_description,
        "status": "draft",
        "assigned_at": datetime.now().isoformat(),
    }
    response = supabase.table("tasks").insert(insert_data).execute()
    row = response.data[0]
    return TaskResponse(**{**row, "id": str(row["id"])})

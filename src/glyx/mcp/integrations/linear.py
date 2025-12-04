"""Linear integration models and GraphQL client for Agent Activities."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel, Field

from agents.items import ItemHelpers, MessageOutputItem

from glyx_python_sdk import GlyxOrchestrator
from glyx_python_sdk.websocket_manager import broadcast_event
from glyx_python_sdk.models.task import Task

logger = logging.getLogger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"


class AgentSessionEvent(BaseModel):
    """Pydantic model for Linear AgentSessionEvent webhook payloads."""

    action: str = Field(..., description="Event action: 'session.created', 'session.updated', etc.")
    session_id: str = Field(..., description="Unique session identifier")
    workspace_id: str = Field(..., description="Linear workspace ID")
    organization_id: str = Field(default="", description="Organization ID if available")
    data: dict[str, Any] = Field(default_factory=dict, description="Event-specific payload data")
    timestamp: str = Field(..., description="ISO8601 timestamp of the event")


class LinearGraphQLClient:
    """GraphQL client for emitting Agent Activities to Linear."""

    def __init__(self, api_key: str) -> None:
        """Initialize Linear GraphQL client.

        Args:
            api_key: Linear API key (required)
        """
        self.api_key = api_key
        self._headers = {
            "Authorization": api_key,
            "Content-Type": "application/json",
        }

    async def emit_activity(
        self,
        session_id: str,
        activity_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Emit an Agent Activity to Linear.

        Args:
            session_id: Linear agent session ID
            activity_type: Type of activity (e.g., 'thought', 'result', 'error')
            content: Activity content/text
            metadata: Optional metadata dictionary

        Returns:
            GraphQL response data

        Raises:
            httpx.HTTPError: If the GraphQL request fails
        """
        mutation = """
        mutation CreateAgentActivity($sessionId: String!, $type: String!, $content: String!, $metadata: JSON) {
            agentActivityCreate(
                sessionId: $sessionId
                type: $type
                content: $content
                metadata: $metadata
            ) {
                success
                activity {
                    id
                    type
                    content
                    createdAt
                }
            }
        }
        """

        variables = {
            "sessionId": session_id,
            "type": activity_type,
            "content": content,
            "metadata": metadata or {},
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                LINEAR_API_URL,
                json={"query": mutation, "variables": variables},
                headers=self._headers,
            )
            response.raise_for_status()
            result = response.json()

            if "errors" in result:
                error_msg = "; ".join(e.get("message", "Unknown error") for e in result["errors"])
                raise ValueError(f"GraphQL errors: {error_msg}")

            return result.get("data", {})

    async def acknowledge_session(self, session_id: str, thought: str = "Processing request...") -> dict[str, Any]:
        """Acknowledge a session by emitting a thought activity (required within 10 seconds).

        Args:
            session_id: Linear agent session ID
            thought: Initial thought/acknowledgment message

        Returns:
            GraphQL response data
        """
        return await self.emit_activity(session_id, "thought", thought, {"acknowledged": True})


async def handle_session_task(
    supabase: Any,
    linear_client: LinearGraphQLClient,
    session_id: str,
    workspace_id: str,
    task_description: str,
    organization_id: str = "",
) -> str:
    """Convert a Linear session event into an orchestration task and stream results.

    Args:
        supabase: Supabase client for persistence
        linear_client: Linear GraphQL client
        session_id: Linear agent session ID
        workspace_id: Linear workspace ID
        task_description: Task description from Linear
        organization_id: Organization ID for activities

    Returns:
        Task ID of the created task
    """
    org_id = organization_id or workspace_id
    org_name = f"Linear-{workspace_id[:8]}"

    task = Task(
        title=f"Linear Session: {task_description[:80]}",
        description=task_description,
        status="in_progress",
        created_by="linear-agent",
        linear_session_id=session_id,
        linear_workspace_id=workspace_id,
    )

    task_id = task.task_id

    supabase.table("tasks").insert({
        "id": task_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "created_by": task.created_by,
        "linear_session_id": session_id,
        "linear_workspace_id": workspace_id,
        "organization_id": org_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    await broadcast_event("linear.task.created", {"task_id": task_id, "session_id": session_id})

    asyncio.create_task(
        _orchestrate_and_stream(supabase, linear_client, task_id, task_description, session_id, org_id, org_name)
    )

    return task_id


async def _orchestrate_and_stream(
    supabase: Any,
    linear_client: LinearGraphQLClient,
    task_id: str,
    task_description: str,
    session_id: str,
    organization_id: str,
    organization_name: str,
) -> None:
    """Run orchestration and stream ActivityInsert records back to Linear."""
    try:
        orchestrator = GlyxOrchestrator(
            agent_name="LinearOrchestrator",
            model="openrouter/anthropic/claude-sonnet-4",
            mcp_servers=[],
            session_id=session_id,
        )

        await linear_client.emit_activity(session_id, "thought", "Starting orchestration...")

        output_parts = []
        async for item in orchestrator.run_prompt_streamed_items(task_description):
            if isinstance(item, MessageOutputItem):
                text = ItemHelpers.text_message_output(item)
                output_parts.append(text)
                await linear_client.emit_activity(session_id, "message", text[:500])

        await orchestrator.cleanup()

        final_output = "".join(output_parts) or "Task completed"
        await linear_client.emit_activity(session_id, "result", final_output[:1000])
        _update_task_status(supabase, task_id, "completed")

        activities = _fetch_task_activities(supabase, task_id, organization_id)
        for activity in activities:
            await linear_client.emit_activity(
                session_id,
                activity.get("type", "message").lower(),
                activity.get("content", ""),
                activity.get("metadata"),
            )
    except Exception as e:
        logger.exception(f"Orchestration failed for task {task_id}: {e}")
        await linear_client.emit_activity(session_id, "error", f"Orchestration error: {str(e)}")
        _update_task_status(supabase, task_id, "failed")


def _update_task_status(supabase: Any, task_id: str, status: str) -> None:
    """Update task status in Supabase."""
    supabase.table("tasks").update({
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", task_id).execute()


def _fetch_task_activities(supabase: Any, task_id: str, organization_id: str) -> list[dict[str, Any]]:
    """Fetch activities for a task from Supabase."""
    response = supabase.table("activities").select("*").eq("org_id", organization_id).order("created_at", desc=False).execute()
    return response.data or []

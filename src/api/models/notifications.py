"""Notification payload models."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class TaskNotificationPayload(BaseModel):
    """Payload for task notifications."""

    model_config = ConfigDict(extra="ignore")

    task_id: str
    title: str
    description: str | None = None
    status: str
    assignee_id: str | None = None
    url: str | None = None


class GitHubNotificationPayload(BaseModel):
    """Payload for GitHub notifications."""

    model_config = ConfigDict(extra="ignore")

    event_type: str
    actor: str
    repo: str
    content: str
    url: str | None = None
    metadata: dict[str, Any] | None = None


class AgentNotificationPayload(BaseModel):
    """Payload for agent lifecycle notifications (iOS push via Knock).

    Used for agent-start, agent-needs-input, agent-completed, agent-error workflows.
    """

    model_config = ConfigDict(extra="ignore")

    event_type: str  # "started", "needs_input", "completed", "error"
    agent_type: str  # "claude", "codex", "cursor", "shell"
    session_id: str  # For deep linking: glyx://agent/{session_id}
    task_summary: str  # Brief summary of the task
    urgency: str = "medium"  # "low", "medium", "high", "critical"
    action_required: bool = False
    device_name: str | None = None
    error_message: str | None = None
    execution_time_s: float | None = None
    exit_code: int | None = None
    hitl_request_id: str | None = None  # For HITL deep linking

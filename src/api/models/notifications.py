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

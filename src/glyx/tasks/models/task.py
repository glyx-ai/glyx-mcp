"""Task model for task tracking and orchestration."""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from pydantic.types import Json


class Task(BaseModel):
    """Task model for tracking agent work in orchestration."""

    model_config = ConfigDict(extra='forbid')

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(..., min_length=1, description="Brief task title")
    description: str = Field(..., description="Detailed task description")
    status: Literal["todo", "in_progress", "blocked", "done", "failed"] = Field(
        default="todo", description="Current task status"
    )
    priority: Literal["low", "medium", "high", "critical"] = Field(
        default="medium", description="Task priority level"
    )
    assigned_agent: Optional[str] = Field(
        default=None, description="Agent ID (aider, grok, claude, etc.) assigned to this task"
    )
    created_by: str = Field(..., description="Agent ID that created the task")
    created_at: datetime = Field(default_factory=datetime.now)
    progress_notes: list[str] = Field(default_factory=list, description="Chronological progress updates")
    metadata: Json[dict[str, Any]] = Field(default_factory=dict, description="Additional task metadata as JSON")
    updated_at: datetime = Field(default_factory=datetime.now)

    def add_progress_note(self, note: str) -> None:
        """Add a progress note and update timestamp."""
        self.progress_notes.append(note)
        self.updated_at = datetime.now()

    def assign_to(self, agent_id: str) -> None:
        """Assign task to an agent and update timestamp."""
        self.assigned_agent = agent_id
        self.updated_at = datetime.now()

    def update_status(self, status: Literal["todo", "in_progress", "blocked", "done", "failed"]) -> None:
        """Update task status and timestamp."""
        self.status = status
        self.updated_at = datetime.now()

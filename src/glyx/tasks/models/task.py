"""Task model for orchestration."""

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Task(BaseModel):
    """Task model for tracking agent work."""
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: str
    status: Literal["todo", "in_progress", "blocked", "done", "failed"] = "todo"
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    assigned_agent: str | None = None
    created_by: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    progress_notes: list[str] = Field(default_factory=list)

    def assign_to(self, agent_id: str) -> None:
        """Assign task to an agent."""
        self.assigned_agent = agent_id
        self.updated_at = datetime.now()

    def add_progress_note(self, note: str) -> None:
        """Add a progress note."""
        self.progress_notes.append(note)
        self.updated_at = datetime.now()

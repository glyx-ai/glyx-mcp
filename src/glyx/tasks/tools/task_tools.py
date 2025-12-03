"""Task tools for orchestration (stub implementation)."""

import json

from glyx.tasks.models.task import Task


async def create_task(task: Task) -> str:
    """Create a new task (stub)."""
    return json.dumps({"task_id": task.task_id, "status": "created"})


async def assign_task(task: Task, agent_id: str) -> str:
    """Assign a task to an agent (stub)."""
    task.assign_to(agent_id)
    return json.dumps({"task_id": task.task_id, "assigned_agent": agent_id})


async def update_task(task: Task) -> str:
    """Update a task (stub)."""
    return json.dumps({"task_id": task.task_id, "status": task.status})

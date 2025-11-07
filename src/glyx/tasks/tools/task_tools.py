"""Task tracking tools for orchestration and progress management."""

from __future__ import annotations

import json
import logging
import time
from typing import Annotated, Any

from fastmcp import Context
from mem0 import MemoryClient
from pydantic import BeforeValidator

from glyx.tasks.models.task import Task
from glyx.tasks.settings import settings

logger = logging.getLogger(__name__)

# Initialize Mem0 client for task persistence
mem0_client = MemoryClient(api_key=settings.mem0_api_key) if settings.mem0_api_key else None


def parse_task(v: Any) -> Task:
    """Parse Task from string, dict, or Task instance."""
    if isinstance(v, Task):
        return v
    elif isinstance(v, str):
        return Task.model_validate_json(v)
    elif isinstance(v, dict):
        return Task.model_validate(v)
    else:
        raise ValueError(f"Cannot parse Task from type {type(v)}")


# Type alias for Task input that accepts JSON string, dict, or Task
TaskInput = Annotated[Task, BeforeValidator(parse_task)]


async def _get_latest_task(task_id: str, user_id: str = "glyx_app_1") -> Task | None:
    """Retrieve the latest version of a task from memory.

    Args:
        task_id: The task ID to search for
        user_id: User identifier for memory segmentation

    Returns:
        Task model if found, None otherwise
    """
    if not mem0_client:
        logger.warning("Memory feature not available")
        return None

    # Search for the task in memory
    memories = mem0_client.search(
        query=f"task_id:{task_id}",
        filters={"user_id": user_id},
    )

    if not memories or not memories.get("results"):
        logger.warning(f"Task not found: {task_id}")
        return None

    # Get the most recent memory entry (first result)
    latest_memory = memories["results"][0]
    task_data = json.loads(latest_memory["memory"])

    # Parse into Task model
    return Task.model_validate_json(task_data)


async def create_task(
    task: TaskInput,
    user_id: str = "glyx_app_1",
    run_id: str = "default",
    ctx: Context | None = None,
) -> str:
    """Create a new task for tracking work in orchestration.

    Args:
        task: Task model to create (accepts JSON string, dict, or Task instance)
        user_id: User identifier for memory segmentation
        run_id: Unique identifier for the current execution run
        ctx: FastMCP context for logging (injected by FastMCP)

    Returns:
        JSON string with task_id and confirmation message
    """
    await ctx.info("Creating task", extra={"title": task.title, "priority": task.priority})

    if not mem0_client:
        return json.dumps({"error": "Memory feature not available - MEM0_API_KEY not configured"})

    # Save to memory
    timestamp = int(time.time())

    memory_dict = {
        "messages": task.model_dump_json(),
        "agent_id": task.created_by,
        "user_id": user_id,
        "run_id": run_id,
        "timestamp": timestamp,
        "metadata": {
            "category": "tasks",
            "task_id": task.task_id,
            "task_status": task.status,
            "priority": task.priority,
        }
    }

    result = mem0_client.add(enable_graph=True, **memory_dict)

    await ctx.info("Task created successfully", extra={"task_id": task.task_id})

    return json.dumps({
        "task_id": task.task_id,
        "status": "created",
        "message": f"Task '{task.title}' created successfully",
        "memory_result": result
    })


async def assign_task(
    task: TaskInput,
    agent_id: str,
    user_id: str = "glyx_app_1",
    run_id: str = "default",
    ctx: Context | None = None,
) -> str:
    """Assign a task to a specific agent.

    Args:
        task: Task model to assign
        agent_id: Agent ID to assign the task to
        user_id: User identifier for memory segmentation
        run_id: Unique identifier for the current execution run
        ctx: FastMCP context for logging (injected by FastMCP)

    Returns:
        JSON string with confirmation message
    """
    await ctx.info("Assigning task", extra={"task_id": task.task_id, "agent_id": agent_id})

    if not mem0_client:
        return json.dumps({"error": "Memory feature not available - MEM0_API_KEY not configured"})

    # Update assignment
    task.assign_to(agent_id)
    task.add_progress_note(f"Task assigned to {agent_id}")

    # Save updated task to memory
    timestamp = int(time.time())

    memory_dict = {
        "messages": task.model_dump_json(),
        "agent_id": agent_id,
        "user_id": user_id,
        "run_id": run_id,
        "timestamp": timestamp,
        "metadata": {
            "category": "tasks",
            "task_id": task.task_id,
            "task_status": task.status,
            "priority": task.priority,
            "assigned_agent": agent_id,
        }
    }

    result = mem0_client.add(enable_graph=True, **memory_dict)

    await ctx.info("Task assigned successfully", extra={"task_id": task.task_id, "agent_id": agent_id})

    return json.dumps({
        "task_id": task.task_id,
        "assigned_agent": agent_id,
        "status": "assigned",
        "message": f"Task '{task.title}' assigned to {agent_id}",
        "memory_result": result
    })


async def update_task(
    task: TaskInput,
    user_id: str = "glyx_app_1",
    run_id: str = "default",
    ctx: Context | None = None,
) -> str:
    """Update a task's status, progress notes, or metadata.

    Args:
        task: Task model with updates applied
        user_id: User identifier for memory segmentation
        run_id: Unique identifier for the current execution run
        ctx: FastMCP context for logging (injected by FastMCP)

    Returns:
        JSON string with updated task details
    """
    await ctx.info("Updating task", extra={"task_id": task.task_id, "status": task.status})

    if not mem0_client:
        return json.dumps({"error": "Memory feature not available - MEM0_API_KEY not configured"})

    # Save updated task to memory
    timestamp = int(time.time())

    memory_dict = {
        "messages": task.model_dump_json(),
        "agent_id": task.assigned_agent or task.created_by,
        "user_id": user_id,
        "run_id": run_id,
        "timestamp": timestamp,
        "metadata": {
            "category": "tasks",
            "task_id": task.task_id,
            "task_status": task.status,
            "priority": task.priority,
        }
    }

    if task.assigned_agent:
        memory_dict["metadata"]["assigned_agent"] = task.assigned_agent

    result = mem0_client.add(enable_graph=True, **memory_dict)

    await ctx.info("Task updated successfully", extra={"task_id": task.task_id, "status": task.status})

    return json.dumps({
        "task_id": task.task_id,
        "status": task.status,
        "title": task.title,
        "assigned_agent": task.assigned_agent,
        "progress_notes": task.progress_notes,
        "message": f"Task '{task.title}' updated successfully",
        "memory_result": result
    })

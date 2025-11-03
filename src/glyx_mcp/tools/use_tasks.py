"""Task tracking tools for orchestration and progress management."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Literal, Optional

from fastmcp import Context
from pydantic import Field

from glyx_mcp.models.task import Task
from glyx_mcp.tools.use_memory import mem0_client

logger = logging.getLogger(__name__)


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

    try:
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
    except Exception as e:
        logger.error(f"Error retrieving task {task_id}: {e}")
        return None


async def create_task(
    title: Annotated[str, Field(description="Brief task title")],
    description: Annotated[str, Field(description="Detailed task description")],
    user_id: Annotated[str, Field(description="User identifier for memory segmentation")] = "glyx_app_1",
    run_id: Annotated[str, Field(description="Unique identifier for the current execution run")] = "default",
    priority: Annotated[
        Literal["low", "medium", "high", "critical"],
        Field(description="Task priority level")
    ] = "medium",
    created_by: Annotated[str, Field(description="Agent ID that created the task")] = "orchestrator",
    metadata: Annotated[Optional[dict[str, Any]], Field(description="Additional task metadata")] = None,
    ctx: Context | None = None,
) -> str:
    """Create a new task for tracking work in orchestration.

    Args:
        title: Brief task title
        description: Detailed task description
        user_id: User identifier for memory segmentation
        run_id: Unique identifier for the current execution run
        priority: Task priority level (low, medium, high, critical)
        created_by: Agent ID that created the task
        metadata: Additional task metadata
        ctx: FastMCP context for logging (injected by FastMCP)

    Returns:
        JSON string with task_id and confirmation message
    """
    if ctx:
        await ctx.info("Creating task", extra={"title": title, "priority": priority})

    if not mem0_client:
        return json.dumps({"error": "Memory feature not available - MEM0_API_KEY not configured"})

    # Create new Task instance
    task = Task(
        title=title,
        description=description,
        priority=priority,
        created_by=created_by,
        metadata=metadata or {},
    )

    # Save to memory
    import time
    timestamp = int(time.time())

    memory_dict = {
        "messages": task.model_dump_json(),
        "agent_id": created_by,
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

    try:
        result = mem0_client.add(enable_graph=True, **memory_dict)

        if ctx:
            await ctx.info("Task created successfully", extra={"task_id": task.task_id})

        return json.dumps({
            "task_id": task.task_id,
            "status": "created",
            "message": f"Task '{title}' created successfully",
            "memory_result": result
        })
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        return json.dumps({"error": f"Failed to create task: {str(e)}"})


async def assign_task(
    task_id: Annotated[str, Field(description="The task ID to assign")],
    agent_id: Annotated[str, Field(description="Agent ID to assign the task to (e.g., 'aider', 'grok', 'claude')")],
    user_id: Annotated[str, Field(description="User identifier for memory segmentation")] = "glyx_app_1",
    run_id: Annotated[str, Field(description="Unique identifier for the current execution run")] = "default",
    ctx: Context | None = None,
) -> str:
    """Assign a task to a specific agent.

    Args:
        task_id: The task ID to assign
        agent_id: Agent ID to assign the task to
        user_id: User identifier for memory segmentation
        run_id: Unique identifier for the current execution run
        ctx: FastMCP context for logging (injected by FastMCP)

    Returns:
        JSON string with confirmation message
    """
    if ctx:
        await ctx.info("Assigning task", extra={"task_id": task_id, "agent_id": agent_id})

    if not mem0_client:
        return json.dumps({"error": "Memory feature not available - MEM0_API_KEY not configured"})

    # Retrieve the current task
    task = await _get_latest_task(task_id, user_id)
    if not task:
        return json.dumps({"error": f"Task not found: {task_id}"})

    # Update assignment
    task.assign_to(agent_id)
    task.add_progress_note(f"Task assigned to {agent_id}")

    # Save updated task to memory
    import time
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

    try:
        result = mem0_client.add(enable_graph=True, **memory_dict)

        if ctx:
            await ctx.info("Task assigned successfully", extra={"task_id": task_id, "agent_id": agent_id})

        return json.dumps({
            "task_id": task_id,
            "assigned_agent": agent_id,
            "status": "assigned",
            "message": f"Task '{task.title}' assigned to {agent_id}",
            "memory_result": result
        })
    except Exception as e:
        logger.error(f"Error assigning task: {e}")
        return json.dumps({"error": f"Failed to assign task: {str(e)}"})


async def update_task(
    task_id: Annotated[str, Field(description="The task ID to update")],
    user_id: Annotated[str, Field(description="User identifier for memory segmentation")] = "glyx_app_1",
    run_id: Annotated[str, Field(description="Unique identifier for the current execution run")] = "default",
    status: Annotated[
        Optional[Literal["todo", "in_progress", "blocked", "done", "failed"]],
        Field(description="New task status")
    ] = None,
    progress_notes: Annotated[Optional[str], Field(description="Progress update note")] = None,
    metadata: Annotated[Optional[dict[str, Any]], Field(description="Additional metadata to merge")] = None,
    ctx: Context | None = None,
) -> str:
    """Update a task's status, add progress notes, or update metadata.

    Args:
        task_id: The task ID to update
        user_id: User identifier for memory segmentation
        run_id: Unique identifier for the current execution run
        status: New task status (optional)
        progress_notes: Progress update note to add (optional)
        metadata: Additional metadata to merge (optional)
        ctx: FastMCP context for logging (injected by FastMCP)

    Returns:
        JSON string with updated task details
    """
    if ctx:
        await ctx.info("Updating task", extra={"task_id": task_id, "status": status})

    if not mem0_client:
        return json.dumps({"error": "Memory feature not available - MEM0_API_KEY not configured"})

    # Retrieve the current task
    task = await _get_latest_task(task_id, user_id)
    if not task:
        return json.dumps({"error": f"Task not found: {task_id}"})

    # Apply updates
    if status:
        task.update_status(status)

    if progress_notes:
        task.add_progress_note(progress_notes)

    if metadata:
        task.metadata.update(metadata)
        task.updated_at = task.updated_at  # Touch timestamp

    # Save updated task to memory
    import time
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

    try:
        result = mem0_client.add(enable_graph=True, **memory_dict)

        if ctx:
            await ctx.info("Task updated successfully", extra={"task_id": task_id, "status": task.status})

        return json.dumps({
            "task_id": task_id,
            "status": task.status,
            "title": task.title,
            "assigned_agent": task.assigned_agent,
            "progress_notes": task.progress_notes,
            "message": f"Task '{task.title}' updated successfully",
            "memory_result": result
        })
    except Exception as e:
        logger.error(f"Error updating task: {e}")
        return json.dumps({"error": f"Failed to update task: {str(e)}"})

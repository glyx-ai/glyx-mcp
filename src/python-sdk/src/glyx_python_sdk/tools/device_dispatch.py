"""
Tools for dispatching tasks to paired devices via Supabase Realtime.

The iOS app calls these MCP tools, which insert into agent_tasks table.
The MCP executor on the user's Mac subscribes to Supabase Realtime and executes tasks.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from knockapi import Knock
from supabase import create_client

from glyx_python_sdk.settings import settings

logger = logging.getLogger(__name__)


def _send_task_dispatched_notification(
    user_id: str,
    task_id: str,
    agent_type: str,
    device_id: str,
    prompt: str | None = None,
) -> None:
    """Send notification when a task is dispatched to a device."""
    api_key = settings.knock_api_key
    if not api_key:
        logger.debug("[KNOCK] No API key configured, skipping dispatch notification")
        return

    knock = Knock(api_key=api_key)
    payload = {
        "event_type": "started",
        "agent_type": agent_type,
        "session_id": task_id,
        "task_summary": (prompt[:200] if prompt else f"Task sent to {agent_type}"),
        "urgency": "low",
        "action_required": False,
        "device_name": device_id,
    }

    try:
        knock.workflows.trigger(
            key="agent-start",
            recipients=[user_id],
            data=payload,
        )
        logger.info(f"[KNOCK] Triggered agent-start for task {task_id}")
    except Exception as e:
        logger.warning(f"[KNOCK] Failed to send dispatch notification: {e}")


def _get_supabase():
    """Get Supabase client."""
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


async def dispatch_task(
    device_id: str,
    agent_type: str,
    prompt: str,
    cwd: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict:
    """
    Dispatch a task to a local agent on a paired device.

    The task is inserted into the agent_tasks table, which triggers
    a Supabase Realtime notification to the MCP executor running on the device.

    Args:
        device_id: The target device ID (from paired_devices table)
        agent_type: Agent type (claude, aider, cursor, codex, etc.)
        prompt: The task prompt to send to the agent
        cwd: Optional working directory for the task
        user_id: The user ID (from auth context)

    Returns:
        Task creation result with task_id
    """
    if not user_id:
        return {"error": "User authentication required"}

    logger.info(f"[DISPATCH] dispatch_task (internal) - cwd={cwd}")

    supabase = _get_supabase()

    # Create task payload
    payload = {"prompt": prompt}
    if cwd:
        payload["cwd"] = cwd
        logger.info(f"[DISPATCH] Added cwd to payload: {cwd}")

    task_data = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "device_id": device_id,
        "agent_type": agent_type,
        "task_type": "prompt",
        "payload": payload,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    result = supabase.table("agent_tasks").insert(task_data).execute()

    if result.data:
        logger.info(f"Dispatched task {task_data['id']} to device {device_id}")

        # Send iOS push notification
        _send_task_dispatched_notification(
            user_id=user_id,
            task_id=task_data["id"],
            agent_type=agent_type,
            device_id=device_id,
            prompt=prompt,
        )

        return {
            "task_id": task_data["id"],
            "device_id": device_id,
            "agent_type": agent_type,
            "status": "pending",
            "message": f"Task dispatched to {agent_type} on device {device_id}",
        }
    else:
        logger.error(f"Failed to dispatch task: {result}")
        return {"error": "Failed to dispatch task"}


async def run_on_device(
    device_id: str,
    command: str,
    cwd: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict:
    """
    Run a shell command on a paired device.

    Args:
        device_id: The target device ID
        command: Shell command to execute
        cwd: Optional working directory
        user_id: The user ID (from auth context)

    Returns:
        Task creation result
    """
    if not user_id:
        return {"error": "User authentication required"}

    supabase = _get_supabase()

    payload = {"command": command}
    if cwd:
        payload["cwd"] = cwd

    task_data = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "device_id": device_id,
        "agent_type": "shell",
        "task_type": "command",
        "payload": payload,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    result = supabase.table("agent_tasks").insert(task_data).execute()

    if result.data:
        return {
            "task_id": task_data["id"],
            "device_id": device_id,
            "status": "pending",
            "message": f"Command dispatched to device {device_id}",
        }
    else:
        return {"error": "Failed to dispatch command"}


async def start_agent(
    device_id: str,
    agent_type: str,
    cwd: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict:
    """
    Start an AI agent on a paired device.

    Args:
        device_id: The target device ID
        agent_type: Agent to start (claude, aider, cursor, etc.)
        cwd: Optional working directory
        user_id: The user ID (from auth context)

    Returns:
        Task creation result
    """
    if not user_id:
        return {"error": "User authentication required"}

    supabase = _get_supabase()

    payload = {}
    if cwd:
        payload["cwd"] = cwd

    task_data = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "device_id": device_id,
        "agent_type": agent_type,
        "task_type": "start",
        "payload": payload,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    result = supabase.table("agent_tasks").insert(task_data).execute()

    if result.data:
        return {
            "task_id": task_data["id"],
            "device_id": device_id,
            "agent_type": agent_type,
            "status": "pending",
            "message": f"Starting {agent_type} on device {device_id}",
        }
    else:
        return {"error": f"Failed to start {agent_type}"}


async def stop_agent(
    device_id: str,
    agent_type: str,
    user_id: Optional[str] = None,
) -> dict:
    """
    Stop a running agent on a paired device.

    Args:
        device_id: The target device ID
        agent_type: Agent to stop
        user_id: The user ID (from auth context)

    Returns:
        Task creation result
    """
    if not user_id:
        return {"error": "User authentication required"}

    supabase = _get_supabase()

    task_data = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "device_id": device_id,
        "agent_type": agent_type,
        "task_type": "stop",
        "payload": {},
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    result = supabase.table("agent_tasks").insert(task_data).execute()

    if result.data:
        return {
            "task_id": task_data["id"],
            "device_id": device_id,
            "agent_type": agent_type,
            "status": "pending",
            "message": f"Stopping {agent_type} on device {device_id}",
        }
    else:
        return {"error": f"Failed to stop {agent_type}"}


async def list_devices(user_id: Optional[str] = None) -> dict:
    """
    List all paired devices for the current user.

    Args:
        user_id: The user ID (from auth context)

    Returns:
        List of paired devices
    """
    if not user_id:
        return {"error": "User authentication required"}

    supabase = _get_supabase()

    result = (
        supabase.table("paired_devices")
        .select("id, name, relay_url, status, hostname, os, paired_at")
        .eq("user_id", user_id)
        .execute()
    )

    if result.data:
        return {"devices": result.data, "count": len(result.data)}
    else:
        return {"devices": [], "count": 0}


async def get_device_status(device_id: str, user_id: Optional[str] = None) -> dict:
    """
    Get detailed status of a specific device.

    Args:
        device_id: The device ID to check
        user_id: The user ID (from auth context)

    Returns:
        Device status information
    """
    if not user_id:
        return {"error": "User authentication required"}

    supabase = _get_supabase()

    # Get device info
    device_result = (
        supabase.table("paired_devices")
        .select("*")
        .eq("id", device_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if not device_result.data:
        return {"error": "Device not found"}

    # Get recent tasks for this device
    tasks_result = (
        supabase.table("agent_tasks")
        .select("id, agent_type, task_type, status, created_at, updated_at")
        .eq("device_id", device_id)
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )

    return {
        "device": device_result.data,
        "recent_tasks": tasks_result.data if tasks_result.data else [],
    }


async def get_task_status(task_id: str, user_id: Optional[str] = None) -> dict:
    """
    Get status of a dispatched task.

    Args:
        task_id: The task ID to check
        user_id: The user ID (from auth context)

    Returns:
        Task status and result
    """
    if not user_id:
        return {"error": "User authentication required"}

    supabase = _get_supabase()

    result = (
        supabase.table("agent_tasks")
        .select("*")
        .eq("id", task_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if result.data:
        return {"task": result.data}
    else:
        return {"error": "Task not found"}



"""
Local agent executor - runs tasks on the local machine.

Subscribes to Supabase Realtime for agent_tasks where device_id matches
this machine, executes tasks using ComposableAgent, and sends notifications.

This runs as part of the FastAPI server lifespan, not as a separate daemon.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from glyx_python_sdk.agent_types import AgentKey
from glyx_python_sdk.composable_agents import ComposableAgent
from glyx_python_sdk.settings import settings
from knockapi import Knock
from supabase._async.client import AsyncClient
from supabase._async.client import create_client as create_async_client

logger = logging.getLogger(__name__)

# Map agent_type strings from database to AgentKey enum
AGENT_KEY_MAP: dict[str, AgentKey] = {
    "claude": AgentKey.CLAUDE,
    "claude-code": AgentKey.CLAUDE,
    "cursor": AgentKey.CURSOR,
    "codex": AgentKey.CODEX,
    "aider": AgentKey.AIDER,
    "gemini": AgentKey.GEMINI,
    "opencode": AgentKey.OPENCODE,
    "grok": AgentKey.GROK,
}


def _load_device_id() -> str | None:
    """Load device ID from env or ~/.glyx/device_id."""
    # Check env first
    device_id = os.environ.get("GLYX_DEVICE_ID")
    if device_id:
        return device_id.lower()

    # Check file
    device_id_file = os.path.expanduser("~/.glyx/device_id")
    try:
        if os.path.exists(device_id_file):
            with open(device_id_file) as f:
                device_id = f.read().strip()
                if device_id:
                    return device_id.lower()
    except Exception as e:
        logger.debug(f"Could not read device ID from file: {e}")

    return None


def _send_notification(
    user_id: str,
    task_id: str,
    workflow_key: str,
    agent_type: str = "agent",
    task_summary: str = "",
    device_name: str | None = None,
    error_message: str | None = None,
    execution_time_s: float | None = None,
) -> None:
    """Send agent notification via Knock."""
    api_key = settings.knock_api_key
    if not api_key:
        logger.warning(f"[KNOCK] No API key, skipping {workflow_key}")
        return

    knock = Knock(api_key=api_key)

    event_type_map = {
        "agent-start": "started",
        "agent-completed": "completed",
        "agent-error": "error",
    }

    payload = {
        "event_type": event_type_map.get(workflow_key, workflow_key),
        "agent_type": agent_type,
        "session_id": task_id,
        "task_summary": task_summary[:200] if task_summary else "",
        "urgency": "high" if workflow_key == "agent-error" else "medium",
        "action_required": workflow_key == "agent-error",
    }

    if device_name:
        payload["device_name"] = device_name
    if error_message:
        payload["error_message"] = error_message[:500]
    if execution_time_s is not None:
        payload["execution_time_s"] = execution_time_s

    try:
        knock.workflows.trigger(key=workflow_key, recipients=[user_id], data=payload)
        logger.info(f"[KNOCK] Triggered {workflow_key} for user {user_id}")
    except Exception as e:
        logger.warning(f"[KNOCK] Failed: {e}")


class LocalExecutor:
    """Executes agent tasks locally via Supabase Realtime subscription."""

    def __init__(self, device_id: str):
        self.device_id = device_id
        self.supabase: AsyncClient | None = None
        self.running = False
        self.task_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._channel = None
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start the executor - subscribe to Realtime and process tasks."""
        if not settings.supabase_url or not settings.supabase_service_role_key:
            logger.warning("[LocalExecutor] Missing Supabase credentials, not starting")
            return

        logger.info(f"[LocalExecutor] Starting for device: {self.device_id}")
        logger.info(f"[LocalExecutor] Knock configured: {bool(settings.knock_api_key)}")

        self.supabase = await create_async_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
        self.running = True

        # Subscribe to Realtime
        self._channel = self.supabase.channel(f"executor-{self.device_id}")
        self._channel.on_postgres_changes(
            event="INSERT",
            schema="public",
            table="agent_tasks",
            callback=self._on_task_insert,
        )
        await self._channel.subscribe()
        logger.info(f"[LocalExecutor] Subscribed to Realtime")

        # Start task processor
        processor = asyncio.create_task(self._process_tasks())
        self._tasks.append(processor)

        # Poll for any pending tasks on startup
        await self._poll_pending_tasks()

    async def stop(self) -> None:
        """Stop the executor."""
        logger.info("[LocalExecutor] Stopping...")
        self.running = False

        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if self._channel:
            await self._channel.unsubscribe()

        logger.info("[LocalExecutor] Stopped")

    def _on_task_insert(self, payload: dict[str, Any]) -> None:
        """Handle new task from Realtime."""
        # Extract task data (handle different payload formats)
        new_task = payload.get("new", {})
        if not new_task:
            data = payload.get("data", {})
            if isinstance(data, dict):
                new_task = data.get("record", {})
            if not new_task:
                new_task = payload.get("record", {})

        if not new_task:
            logger.warning("[LocalExecutor] No task data in payload")
            return

        task_id = new_task.get("id")
        task_device_id = new_task.get("device_id")
        task_status = new_task.get("status")

        # Only process tasks for this device that are pending
        if task_device_id != self.device_id:
            return
        if task_status != "pending":
            return

        logger.info(f"[LocalExecutor] Queuing task {task_id}")
        try:
            self.task_queue.put_nowait(new_task)
        except asyncio.QueueFull:
            logger.error(f"[LocalExecutor] Queue full, dropping task {task_id}")

    async def _poll_pending_tasks(self) -> None:
        """Poll for pending tasks on startup."""
        try:
            result = (
                await self.supabase.table("agent_tasks")
                .select("*")
                .eq("device_id", self.device_id)
                .eq("status", "pending")
                .execute()
            )
            if result.data:
                logger.info(f"[LocalExecutor] Found {len(result.data)} pending tasks")
                for task in result.data:
                    self.task_queue.put_nowait(task)
        except Exception as e:
            logger.error(f"[LocalExecutor] Poll failed: {e}")

    async def _process_tasks(self) -> None:
        """Process tasks from the queue."""
        while self.running:
            try:
                task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                await self._execute_task(task)
                self.task_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[LocalExecutor] Task processing error: {e}")

    async def _execute_task(self, task: dict[str, Any]) -> None:
        """Execute a single task."""
        task_id = task["id"]
        agent_type = task.get("agent_type", "shell")
        task_type = task.get("task_type", "command")
        payload = task.get("payload", {})
        user_id = task.get("user_id")
        device_name = task.get("device_name")

        logger.info(f"[{task_id}] Executing: agent={agent_type}, type={task_type}")

        cwd = payload.get("cwd") or payload.get("working_dir")
        prompt = payload.get("prompt", "")

        # Update status to running
        await self._update_status(task_id, "running")

        # Send start notification
        if user_id:
            _send_notification(
                user_id=user_id,
                task_id=task_id,
                workflow_key="agent-start",
                agent_type=agent_type,
                task_summary=prompt[:200] if prompt else "Task started",
                device_name=device_name,
            )

        agent_key = AGENT_KEY_MAP.get(agent_type)

        if agent_key and task_type == "prompt" and prompt:
            exit_code, output, exec_time = await self._run_agent(
                task_id, agent_key, prompt, cwd, user_id, device_name
            )
        else:
            # Unsupported task type
            await self._update_status(task_id, "failed", error="Unsupported task type")
            return

        # Update final status
        final_status = "completed" if exit_code == 0 else "failed"
        await self._update_status(task_id, final_status, exit_code=exit_code)

        # Send completion notification
        if user_id:
            _send_notification(
                user_id=user_id,
                task_id=task_id,
                workflow_key="agent-error" if exit_code != 0 else "agent-completed",
                agent_type=agent_type,
                task_summary=prompt[:200] if prompt else "Task completed",
                device_name=device_name,
                execution_time_s=exec_time,
            )

    async def _run_agent(
        self,
        task_id: str,
        agent_key: AgentKey,
        prompt: str,
        cwd: str | None,
        user_id: str | None,
        device_name: str | None,
    ) -> tuple[int, str, float]:
        """Run an agent and stream output."""
        import time

        start_time = time.time()
        agent = ComposableAgent.from_key(agent_key)

        task_config = {
            "prompt": prompt,
            "working_dir": cwd or os.getcwd(),
            "user_id": user_id,
            "session_id": task_id,
            "device_name": device_name,
        }

        full_output = []
        output_buffer = []
        last_flush = time.time()
        exit_code = 0

        try:
            async for event in agent.execute_stream(task_config, timeout=300):
                event_type = event.get("type", "unknown")

                if event_type == "agent_output":
                    content = event.get("content", "")
                    if content:
                        full_output.append(content)
                        output_buffer.append(content + "\n")

                elif event_type == "agent_event":
                    parsed = event.get("event", {})
                    if isinstance(parsed, dict):
                        msg_type = parsed.get("type", "")
                        if msg_type == "assistant":
                            message = parsed.get("message", {})
                            content_blocks = message.get("content", []) if isinstance(message, dict) else []
                            for block in content_blocks:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text = block.get("text", "")
                                    if text:
                                        full_output.append(text)
                                        output_buffer.append(text)

                elif event_type == "agent_complete":
                    exit_code = event.get("exit_code", 0)

                # Flush output buffer periodically
                now = time.time()
                if now - last_flush > 0.5 or len(output_buffer) > 10:
                    if output_buffer:
                        chunk = "".join(output_buffer)
                        await self._update_status(task_id, output=chunk)
                        output_buffer.clear()
                        last_flush = now

            # Flush remaining
            if output_buffer:
                await self._update_status(task_id, output="".join(output_buffer))

        except Exception as e:
            logger.error(f"[{task_id}] Agent execution failed: {e}")
            return 1, str(e), time.time() - start_time

        return exit_code, "\n".join(full_output), time.time() - start_time

    async def _update_status(
        self,
        task_id: str,
        status: str | None = None,
        output: str | None = None,
        error: str | None = None,
        exit_code: int | None = None,
    ) -> None:
        """Update task status in Supabase."""
        from datetime import UTC, datetime

        update_data: dict[str, Any] = {"updated_at": datetime.now(UTC).isoformat()}

        if status:
            update_data["status"] = status
            if status == "running":
                update_data["started_at"] = datetime.now(UTC).isoformat()
            elif status in ("completed", "failed"):
                update_data["completed_at"] = datetime.now(UTC).isoformat()

        if error:
            update_data["error"] = error

        if exit_code is not None:
            update_data["exit_code"] = exit_code

        # For output, we need to append
        if output:
            try:
                existing = (
                    await self.supabase.table("agent_tasks")
                    .select("output")
                    .eq("id", task_id)
                    .single()
                    .execute()
                )
                existing_output = existing.data.get("output") or "" if existing.data else ""
                update_data["output"] = existing_output + output
            except Exception:
                update_data["output"] = output

        try:
            await self.supabase.table("agent_tasks").update(update_data).eq("id", task_id).execute()
        except Exception as e:
            logger.error(f"[{task_id}] Failed to update status: {e}")


# Global executor instance
_executor: LocalExecutor | None = None


async def start_local_executor() -> None:
    """Start the local executor if device_id is configured."""
    global _executor

    device_id = _load_device_id()
    if not device_id:
        logger.info("[LocalExecutor] No device_id found, local execution disabled")
        return

    logger.info(f"[LocalExecutor] Starting for device: {device_id}")
    _executor = LocalExecutor(device_id)
    await _executor.start()


async def stop_local_executor() -> None:
    """Stop the local executor."""
    global _executor

    if _executor:
        await _executor.stop()
        _executor = None

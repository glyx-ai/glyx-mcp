"""
Local agent executor — runs tasks on the local machine.

Subscribes to Supabase Realtime for agent_tasks where device_id matches
this machine, executes tasks using ComposableAgent, and sends notifications.

Auth modes (in priority order):
  1. SERVICE_ROLE  — SUPABASE_SERVICE_ROLE_KEY from env (development only)
  2. USER_TOKEN    — access + refresh token from ~/.glyx/session (end users)
  3. UNPROVISIONED — waits for iOS to POST /api/auth/provision after QR pairing
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from glyx_python_sdk.agent_types import AGENT_KEY_MAP
from glyx_python_sdk.composable_agents import ComposableAgent
from glyx_python_sdk.settings import settings
from knockapi import Knock
from supabase._async.client import AsyncClient
from supabase._async.client import create_client as create_async_client

from api.session import (
    AuthMode,
    SessionTokens,
    TOKEN_REFRESH_INTERVAL_SECONDS,
    load_session,
    refresh_session,
    resolve_auth_mode,
    save_session,
    validate_access_token,
)

logger = logging.getLogger(__name__)

# Signalled by POST /api/auth/provision to wake the provision watcher
_provision_event: asyncio.Event | None = None


# ---------------------------------------------------------------------------
# Device ID loader
# ---------------------------------------------------------------------------


def _load_device_id() -> str | None:
    """Load device ID from env or ~/.glyx/device_id."""
    device_id = os.environ.get("GLYX_DEVICE_ID")
    if device_id:
        return device_id.lower()

    path = os.path.expanduser("~/.glyx/device_id")
    try:
        with open(path) as f:
            value = f.read().strip()
            return value.lower() if value else None
    except FileNotFoundError:
        return None


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


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

    payload: dict[str, Any] = {
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


# ---------------------------------------------------------------------------
# LocalExecutor
# ---------------------------------------------------------------------------


class LocalExecutor:
    """Executes agent tasks locally via Supabase Realtime subscription."""

    def __init__(self, device_id: str) -> None:
        self.device_id = device_id
        self.supabase: AsyncClient | None = None
        self.running = False
        self.auth_mode = AuthMode.UNPROVISIONED
        self.task_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._channel: Any = None
        self._tasks: list[asyncio.Task[None]] = []
        self._refresh_token: str | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the executor. Resolves auth mode and connects to Realtime."""
        if not settings.supabase_url:
            logger.warning("[Executor] Missing SUPABASE_URL, not starting")
            return

        logger.info(f"[Executor] Device: {self.device_id}")
        logger.info(f"[Executor] Knock: {bool(settings.knock_api_key)}")

        mode = resolve_auth_mode()

        if mode == AuthMode.SERVICE_ROLE:
            await self._start_with_service_role()
        elif mode == AuthMode.USER_TOKEN:
            await self._start_with_user_token()
        else:
            logger.info("[Executor] Waiting for iOS to provision via QR pairing...")
            self._spawn(self._wait_for_provision())

    async def stop(self) -> None:
        """Stop the executor and clean up."""
        logger.info("[Executor] Stopping...")
        self.running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._channel:
            await self._channel.unsubscribe()
        logger.info("[Executor] Stopped")

    # ------------------------------------------------------------------
    # Auth strategies
    # ------------------------------------------------------------------

    async def _start_with_service_role(self) -> None:
        """Connect using service role key (development only)."""
        logger.info("[Executor] Auth: service_role (development)")
        self.auth_mode = AuthMode.SERVICE_ROLE
        self.supabase = await create_async_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
        await self._subscribe_and_run()

    async def _start_with_user_token(self) -> bool:
        """Connect using user-scoped session from ~/.glyx/session. Returns success."""
        tokens = load_session()
        if not tokens:
            return False

        valid_token = self._ensure_valid_token(tokens)
        if not valid_token:
            logger.warning("[Executor] Stored session invalid, refresh failed")
            return False

        logger.info("[Executor] Auth: user_token")
        self.auth_mode = AuthMode.USER_TOKEN
        self._refresh_token = valid_token.refresh_token

        self.supabase = await create_async_client(
            settings.supabase_url,
            settings.supabase_anon_key,
        )
        await self.supabase.auth.set_session(valid_token.access_token, valid_token.refresh_token)
        await self._subscribe_and_run()
        self._spawn(self._token_refresh_loop())
        return True

    def _ensure_valid_token(self, tokens: SessionTokens) -> SessionTokens | None:
        """Validate access token; refresh if expired."""
        if validate_access_token(tokens.access_token):
            return tokens
        refreshed = refresh_session(tokens.refresh_token)
        return refreshed

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    async def _token_refresh_loop(self) -> None:
        """Periodically refresh the access token before it expires."""
        while self.running and self.auth_mode == AuthMode.USER_TOKEN:
            await asyncio.sleep(TOKEN_REFRESH_INTERVAL_SECONDS)
            if not self._refresh_token:
                continue

            refreshed = refresh_session(self._refresh_token)
            if refreshed and self.supabase:
                self._refresh_token = refreshed.refresh_token
                await self.supabase.auth.set_session(refreshed.access_token, refreshed.refresh_token)
                logger.info("[Executor] Token refreshed")
            else:
                logger.error("[Executor] Token refresh failed, re-provisioning needed")
                self.auth_mode = AuthMode.UNPROVISIONED

    # ------------------------------------------------------------------
    # Provision watcher
    # ------------------------------------------------------------------

    async def _wait_for_provision(self) -> None:
        """Block until iOS provisions credentials, then start."""
        global _provision_event
        _provision_event = asyncio.Event()

        while self.auth_mode == AuthMode.UNPROVISIONED:
            try:
                await asyncio.wait_for(_provision_event.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pass
            _provision_event.clear()

            if await self._start_with_user_token():
                logger.info("[Executor] Provisioned — now running")
                return

    # ------------------------------------------------------------------
    # Realtime subscription
    # ------------------------------------------------------------------

    async def _subscribe_and_run(self) -> None:
        """Subscribe to Realtime and start the task processor."""
        self.running = True
        self._channel = self.supabase.channel(f"executor-{self.device_id}")
        self._channel.on_postgres_changes(
            event="INSERT",
            schema="public",
            table="agent_tasks",
            callback=self._on_task_insert,
        )
        await self._channel.subscribe()
        logger.info(f"[Executor] Subscribed to Realtime ({self.auth_mode})")

        self._spawn(self._process_tasks())
        await self._poll_pending_tasks()

    def _on_task_insert(self, payload: dict[str, Any]) -> None:
        """Handle new task from Realtime."""
        new_task = (
            payload.get("new")
            or (payload.get("data", {}) or {}).get("record")
            or payload.get("record")
            or {}
        )
        if not new_task:
            logger.warning("[Executor] Empty Realtime payload")
            return

        if new_task.get("device_id") != self.device_id:
            return
        if new_task.get("status") != "pending":
            return

        task_id = new_task.get("id")
        logger.info(f"[Executor] Queuing task {task_id}")
        try:
            self.task_queue.put_nowait(new_task)
        except asyncio.QueueFull:
            logger.error(f"[Executor] Queue full, dropping task {task_id}")

    async def _poll_pending_tasks(self) -> None:
        """Pick up any pending tasks from before we started."""
        try:
            result = (
                await self.supabase.table("agent_tasks")
                .select("*")
                .eq("device_id", self.device_id)
                .eq("status", "pending")
                .execute()
            )
            for task in result.data or []:
                self.task_queue.put_nowait(task)
            if result.data:
                logger.info(f"[Executor] Found {len(result.data)} pending tasks")
        except Exception as e:
            logger.error(f"[Executor] Poll failed: {e}")

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    async def _process_tasks(self) -> None:
        """Process tasks from the queue."""
        while self.running:
            try:
                task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            try:
                await self._execute_task(task)
            except Exception as e:
                logger.error(f"[Executor] Task processing error: {e}")
            finally:
                self.task_queue.task_done()

    async def _execute_task(self, task: dict[str, Any]) -> None:
        """Execute a single agent task."""
        task_id = task["id"]
        agent_type = task.get("agent_type", "shell")
        task_type = task.get("task_type", "command")
        payload = task.get("payload", {})
        user_id = task.get("user_id")
        device_name = task.get("device_name")
        prompt = payload.get("prompt", "")
        cwd = payload.get("cwd") or payload.get("working_dir")

        logger.info(f"[{task_id}] Executing: agent={agent_type}, type={task_type}")
        await self._update_status(task_id, "running")

        if user_id:
            _send_notification(
                user_id=user_id,
                task_id=task_id,
                workflow_key="agent-start",
                agent_type=agent_type,
                task_summary=prompt[:200] or "Task started",
                device_name=device_name,
            )

        agent_key = AGENT_KEY_MAP.get(agent_type)
        if not (agent_key and task_type == "prompt" and prompt):
            await self._update_status(task_id, "failed", error="Unsupported task type")
            return

        exit_code, output, exec_time = await self._run_agent(
            task_id, agent_key, prompt, cwd, user_id, device_name,
        )

        final_status = "completed" if exit_code == 0 else "failed"
        await self._update_status(task_id, final_status, exit_code=exit_code)

        if user_id:
            _send_notification(
                user_id=user_id,
                task_id=task_id,
                workflow_key="agent-error" if exit_code != 0 else "agent-completed",
                agent_type=agent_type,
                task_summary=prompt[:200] or "Task completed",
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
        """Run an agent and stream output back to Supabase."""
        start_time = time.time()
        agent = ComposableAgent.from_key(agent_key)

        task_config = {
            "prompt": prompt,
            "working_dir": cwd or os.getcwd(),
            "user_id": user_id,
            "session_id": task_id,
            "device_name": device_name,
        }

        full_output: list[str] = []
        output_buffer: list[str] = []
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
                    self._extract_text_blocks(event, full_output, output_buffer)

                elif event_type == "agent_complete":
                    exit_code = event.get("exit_code", 0)

                # Flush periodically
                now = time.time()
                if (now - last_flush > 0.5 or len(output_buffer) > 10) and output_buffer:
                    await self._update_status(task_id, output="".join(output_buffer))
                    output_buffer.clear()
                    last_flush = now

            if output_buffer:
                await self._update_status(task_id, output="".join(output_buffer))

        except Exception as e:
            logger.error(f"[{task_id}] Agent execution failed: {e}")
            return 1, str(e), time.time() - start_time

        return exit_code, "\n".join(full_output), time.time() - start_time

    @staticmethod
    def _extract_text_blocks(
        event: dict[str, Any],
        full_output: list[str],
        output_buffer: list[str],
    ) -> None:
        """Extract text content blocks from an agent_event."""
        parsed = event.get("event", {})
        if not isinstance(parsed, dict) or parsed.get("type") != "assistant":
            return
        message = parsed.get("message", {})
        if not isinstance(message, dict):
            return
        for block in message.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    full_output.append(text)
                    output_buffer.append(text)

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

        if output:
            try:
                existing = (
                    await self.supabase.table("agent_tasks")
                    .select("output")
                    .eq("id", task_id)
                    .single()
                    .execute()
                )
                existing_output = (existing.data or {}).get("output") or ""
                update_data["output"] = existing_output + output
            except Exception:
                update_data["output"] = output

        try:
            await self.supabase.table("agent_tasks").update(update_data).eq("id", task_id).execute()
        except Exception as e:
            logger.error(f"[{task_id}] Failed to update status: {e}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _spawn(self, coro: Any) -> None:
        """Create and track a background task."""
        self._tasks.append(asyncio.create_task(coro))


# ---------------------------------------------------------------------------
# Module-level API
# ---------------------------------------------------------------------------

_executor: LocalExecutor | None = None


async def start_local_executor() -> None:
    """Start the local executor if device_id is configured."""
    global _executor

    device_id = _load_device_id()
    if not device_id:
        logger.info("[Executor] No device_id found, local execution disabled")
        return

    _executor = LocalExecutor(device_id)
    await _executor.start()


async def stop_local_executor() -> None:
    """Stop the local executor."""
    global _executor
    if _executor:
        await _executor.stop()
        _executor = None


async def notify_session_provisioned() -> None:
    """Called by POST /api/auth/provision to wake the executor."""
    if _provision_event:
        _provision_event.set()

"""Glyx Cloud MCP — per-user agent server with CloudExecutor.

Single-file FastMCP server with owner-only auth via Supabase.
Each user gets their own Cloud Run instance with OWNER_USER_ID set.

The CloudExecutor runs alongside the MCP server, subscribing to
agent_tasks via Supabase Realtime and executing them locally
(same pattern as the LocalExecutor on paired Macs).
"""

import asyncio
import logging
import os
import subprocess
import time
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from glyx_python_sdk.agent_types import AGENT_KEY_MAP
from glyx_python_sdk.composable_agents import ComposableAgent
from starlette.applications import Starlette
from starlette.routing import Mount
from supabase import create_client
from supabase._async.client import AsyncClient
from supabase._async.client import create_client as create_async_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OWNER = os.environ["OWNER_USER_ID"]
SUPA_URL = os.environ.get("SUPABASE_URL", "https://vpopliwokdmpxhmippwc.supabase.co")
SUPA_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "sb_publishable_PFYg1B15pdweWFaL6BRDCQ_SnX-BbZf",
)
SUPA_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class OwnerOnly(TokenVerifier):
    """Only the owner (matched by OWNER_USER_ID env var) can access this server."""

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            user = create_client(SUPA_URL, SUPA_KEY).auth.get_user(token)
            if user.user and str(user.user.id) == OWNER:
                return AccessToken(
                    token=token,
                    client_id="glyx-ios",
                    scopes=[],
                    claims={"sub": str(user.user.id)},
                )
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("glyx-cloud", auth=OwnerOnly())


@mcp.tool()
async def run_command(command: str, cwd: str = "/workspace") -> str:
    """Run a shell command."""
    r = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=120)
    return r.stdout + r.stderr


@mcp.tool()
async def read_file(path: str) -> str:
    """Read a file."""
    with open(path) as f:
        return f.read()


@mcp.tool()
async def write_file(path: str, content: str) -> str:
    """Write a file."""
    with open(path, "w") as f:
        f.write(content)
    return f"Wrote {len(content)} bytes to {path}"


@mcp.tool()
async def list_files(path: str = "/workspace") -> list[dict]:
    """List directory contents."""
    return [
        {"name": e.name, "is_dir": e.is_dir(), "size": e.stat().st_size if e.is_file() else 0}
        for e in os.scandir(path)
    ]


# ---------------------------------------------------------------------------
# CloudExecutor
# ---------------------------------------------------------------------------


class CloudExecutor:
    """Executes agent tasks via Supabase Realtime subscription.

    Mirrors the LocalExecutor: subscribes to agent_tasks where device_id
    matches this cloud instance, runs agents via ComposableAgent, and
    streams output back to Supabase.
    """

    def __init__(self) -> None:
        self.device_id: str | None = None
        self.supabase: AsyncClient | None = None
        self.running = False
        self.task_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._channel: Any = None
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        """Start the executor. Looks up device_id from paired_devices table."""
        supa_key = SUPA_SERVICE_KEY or SUPA_KEY
        self.supabase = await create_async_client(SUPA_URL, supa_key)

        result = (
            await self.supabase.table("paired_devices")
            .select("device_id")
            .eq("user_id", OWNER)
            .eq("device_type", "cloud")
            .limit(1)
            .execute()
        )

        if not result.data:
            logger.info("[CloudExecutor] No cloud device found, polling...")
            self._spawn(self._poll_for_device())
            return

        self.device_id = result.data[0]["device_id"]
        logger.info(f"[CloudExecutor] Device: {self.device_id}")
        await self._subscribe_and_run()

    async def _poll_for_device(self) -> None:
        """Poll for cloud device registration (happens after provisioning completes)."""
        while not self.device_id:
            await asyncio.sleep(10)
            result = (
                await self.supabase.table("paired_devices")
                .select("device_id")
                .eq("user_id", OWNER)
                .eq("device_type", "cloud")
                .limit(1)
                .execute()
            )
            if result.data:
                self.device_id = result.data[0]["device_id"]
                logger.info(f"[CloudExecutor] Found device: {self.device_id}")
                await self._subscribe_and_run()
                return

    async def stop(self) -> None:
        """Stop the executor."""
        self.running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._channel:
            await self._channel.unsubscribe()
        logger.info("[CloudExecutor] Stopped")

    # ------------------------------------------------------------------
    # Realtime subscription
    # ------------------------------------------------------------------

    async def _subscribe_and_run(self) -> None:
        """Subscribe to Realtime and start the task processor."""
        self.running = True
        self._channel = self.supabase.channel(f"cloud-executor-{self.device_id}")
        self._channel.on_postgres_changes(
            event="INSERT",
            schema="public",
            table="agent_tasks",
            callback=self._on_task_insert,
        )
        await self._channel.subscribe()
        logger.info(f"[CloudExecutor] Subscribed to Realtime for device {self.device_id}")

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
            return
        if new_task.get("device_id") != self.device_id:
            return
        if new_task.get("status") != "pending":
            return

        logger.info(f"[CloudExecutor] Queuing task {new_task.get('id')}")
        self.task_queue.put_nowait(new_task)

    async def _poll_pending_tasks(self) -> None:
        """Pick up any pending tasks from before we started."""
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
            logger.info(f"[CloudExecutor] Found {len(result.data)} pending tasks")

    async def _process_tasks(self) -> None:
        """Process tasks from the queue sequentially."""
        while self.running:
            task = await self.task_queue.get()
            await self._execute_task(task)
            self.task_queue.task_done()

    # ------------------------------------------------------------------
    # Task execution via ComposableAgent
    # ------------------------------------------------------------------

    async def _execute_task(self, task: dict[str, Any]) -> None:
        """Execute a single agent task."""
        task_id = task["id"]
        agent_type = task.get("agent_type", "claude-code")
        task_type = task.get("task_type", "command")
        payload = task.get("payload", {})
        user_id = task.get("user_id")
        prompt = payload.get("prompt", "")
        cwd = payload.get("cwd") or payload.get("working_dir") or "/workspace"

        agent_key = AGENT_KEY_MAP.get(agent_type)
        if not (agent_key and task_type == "prompt" and prompt):
            await self._update_status(task_id, "failed", error="Unsupported task type")
            return

        logger.info(f"[{task_id}] Executing: agent={agent_type}, cwd={cwd}")
        await self._update_status(task_id, "running")

        exit_code = await self._run_agent(task_id, agent_key, prompt, cwd, user_id)

        final_status = "completed" if exit_code == 0 else "failed"
        await self._update_status(task_id, final_status, exit_code=exit_code)

    async def _run_agent(
        self,
        task_id: str,
        agent_key: AgentKey,
        prompt: str,
        cwd: str,
        user_id: str | None,
    ) -> int:
        """Run an agent via ComposableAgent and stream output back to Supabase."""
        agent = ComposableAgent.from_key(agent_key)

        task_config = {
            "prompt": prompt,
            "working_dir": cwd,
            "user_id": user_id,
            "session_id": task_id,
        }

        output_buffer: list[str] = []
        last_flush = time.time()
        exit_code = 0

        async for event in agent.execute_stream(task_config, timeout=300):
            event_type = event.get("type", "unknown")

            if event_type == "agent_output":
                content = event.get("content", "")
                if content:
                    output_buffer.append(content + "\n")

            elif event_type == "agent_event":
                self._extract_text_blocks(event, output_buffer)

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

        return exit_code

    @staticmethod
    def _extract_text_blocks(event: dict[str, Any], output_buffer: list[str]) -> None:
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
                    output_buffer.append(text)

    # ------------------------------------------------------------------
    # Supabase updates
    # ------------------------------------------------------------------

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
            existing = (
                await self.supabase.table("agent_tasks")
                .select("output")
                .eq("id", task_id)
                .single()
                .execute()
            )
            existing_output = (existing.data or {}).get("output") or ""
            update_data["output"] = existing_output + output

        await self.supabase.table("agent_tasks").update(update_data).eq("id", task_id).execute()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _spawn(self, coro: Any) -> None:
        """Create and track a background task."""
        self._tasks.append(asyncio.create_task(coro))


# ---------------------------------------------------------------------------
# Entrypoint — MCP server + CloudExecutor
# ---------------------------------------------------------------------------

_executor: CloudExecutor | None = None


async def _start_executor() -> None:
    """Start the CloudExecutor in the background."""
    global _executor
    _executor = CloudExecutor()
    await _executor.start()


@asynccontextmanager
async def _lifespan(app: Any):
    """ASGI lifespan: start executor on startup, stop on shutdown."""
    await _start_executor()
    yield
    if _executor:
        await _executor.stop()


if __name__ == "__main__":
    # Build the ASGI app from FastMCP with streamable-http transport
    mcp_app = mcp.get_asgi_app(transport="streamable-http")

    # Mount the MCP ASGI app under root with lifespan for executor
    wrapper = Starlette(
        lifespan=_lifespan,
        routes=[Mount("/", app=mcp_app)],
    )

    uvicorn.run(wrapper, host="0.0.0.0", port=8080)

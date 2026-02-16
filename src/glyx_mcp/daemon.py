"""
Local daemon that executes tasks dispatched from the iOS app.

Subscribes to Supabase Realtime for agent_tasks where device_id matches
this machine, executes tasks using local agents (Claude Code, shell, etc.),
and streams output back to the database.

Usage:
    glyx-daemon --device-id <uuid>
    glyx-daemon  # Uses GLYX_DEVICE_ID from environment
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import subprocess
import sys
import time
from typing import Any

import httpx
from glyx_python_sdk.settings import settings
from supabase._async.client import AsyncClient
from supabase._async.client import create_client as create_async_client

from supabase import Client, create_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("glyx-daemon")


class TaskExecutor:
    """Executes tasks and streams output back to the server."""

    def __init__(self, api_base_url: str):
        self.api_base_url = api_base_url.rstrip("/")
        self.http_client = httpx.Client(timeout=30.0)

    def update_task_status(
        self,
        task_id: str,
        status: str | None = None,
        output: str | None = None,
        error: str | None = None,
        exit_code: int | None = None,
    ) -> bool:
        """Update task status via the API."""
        url = f"{self.api_base_url}/api/agent-tasks/{task_id}/status"
        payload = {}

        if status:
            payload["status"] = status
        if output:
            payload["output"] = output
        if error:
            payload["error"] = error
        if exit_code is not None:
            payload["exit_code"] = exit_code

        try:
            response = self.http_client.post(url, json=payload)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to update task {task_id}: {e}")
            return False

    def execute_shell_command(
        self,
        task_id: str,
        command: str,
        cwd: str | None = None,
    ) -> tuple[int, str]:
        """Execute a shell command and stream output."""
        logger.info(f"[{task_id}] Executing shell command: {command}")

        # Mark as running
        self.update_task_status(task_id, status="running")

        try:
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=cwd or os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            full_output = []

            # Stream output line by line
            for line in iter(process.stdout.readline, ""):
                if line:
                    full_output.append(line)
                    # Stream this chunk to the server
                    self.update_task_status(task_id, output=line)

            process.wait()
            exit_code = process.returncode

            # Mark as completed or failed
            final_status = "completed" if exit_code == 0 else "failed"
            self.update_task_status(
                task_id,
                status=final_status,
                exit_code=exit_code,
            )

            return exit_code, "".join(full_output)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[{task_id}] Command execution failed: {error_msg}")
            self.update_task_status(
                task_id,
                status="failed",
                error=error_msg,
                exit_code=1,
            )
            return 1, error_msg

    def execute_claude_code(
        self,
        task_id: str,
        prompt: str,
        cwd: str | None = None,
    ) -> tuple[int, str]:
        """Execute a task using Claude Code CLI."""
        logger.info(f"[{task_id}] Executing Claude Code task")

        # Build the Claude Code command
        # Using --print flag for non-interactive output
        cmd = ["claude", "--print", "--dangerously-skip-permissions", prompt]

        # Mark as running
        self.update_task_status(task_id, status="running")

        try:
            process = subprocess.Popen(
                cmd,
                cwd=cwd or os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            full_output = []
            output_buffer = []
            last_flush = time.time()

            # Stream output, buffering to reduce API calls
            for line in iter(process.stdout.readline, ""):
                if line:
                    full_output.append(line)
                    output_buffer.append(line)

                    # Flush buffer every 0.5 seconds or when it's large
                    now = time.time()
                    if now - last_flush > 0.5 or len(output_buffer) > 10:
                        chunk = "".join(output_buffer)
                        self.update_task_status(task_id, output=chunk)
                        output_buffer.clear()
                        last_flush = now

            # Flush remaining buffer
            if output_buffer:
                chunk = "".join(output_buffer)
                self.update_task_status(task_id, output=chunk)

            process.wait()
            exit_code = process.returncode

            # Mark as completed or failed
            final_status = "completed" if exit_code == 0 else "failed"
            self.update_task_status(
                task_id,
                status=final_status,
                exit_code=exit_code,
            )

            return exit_code, "".join(full_output)

        except FileNotFoundError:
            error_msg = "Claude Code CLI not found. Install it with: npm install -g @anthropic/claude-code"
            logger.error(f"[{task_id}] {error_msg}")
            self.update_task_status(
                task_id,
                status="failed",
                error=error_msg,
                exit_code=127,
            )
            return 127, error_msg

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[{task_id}] Claude Code execution failed: {error_msg}")
            self.update_task_status(
                task_id,
                status="failed",
                error=error_msg,
                exit_code=1,
            )
            return 1, error_msg

    def execute_task(self, task: dict[str, Any]) -> None:
        """Execute a task based on its type and agent."""
        task_id = task["id"]
        agent_type = task.get("agent_type", "shell")
        task_type = task.get("task_type", "command")
        payload = task.get("payload", {})

        logger.info(f"[{task_id}] Executing {agent_type}/{task_type} task")

        cwd = payload.get("cwd")

        if agent_type == "shell" or task_type == "command":
            command = payload.get("command", "")
            if command:
                self.execute_shell_command(task_id, command, cwd)
            else:
                self.update_task_status(
                    task_id,
                    status="failed",
                    error="No command provided",
                )

        elif agent_type in ("claude", "claude-code"):
            prompt = payload.get("prompt", "")
            if prompt:
                self.execute_claude_code(task_id, prompt, cwd)
            else:
                self.update_task_status(
                    task_id,
                    status="failed",
                    error="No prompt provided",
                )

        else:
            # For other agent types, default to shell with prompt
            prompt = payload.get("prompt", "")
            if prompt:
                # Try Claude Code for AI agent types
                self.execute_claude_code(task_id, prompt, cwd)
            else:
                self.update_task_status(
                    task_id,
                    status="failed",
                    error=f"Unsupported agent type: {agent_type}",
                )


class GlyxDaemon:
    """
    Daemon that listens for tasks and executes them locally.

    Subscribes to Supabase Realtime for agent_tasks where device_id matches,
    then executes tasks as they arrive.
    """

    # Heartbeat interval in seconds
    HEARTBEAT_INTERVAL = 30

    def __init__(
        self,
        device_id: str,
        api_base_url: str | None = None,
    ):
        # Normalize device_id to lowercase for consistent comparison
        # (iOS saves UUIDs as uppercase, but QR/file uses lowercase)
        self.device_id = device_id.lower()
        self.api_base_url = api_base_url or os.environ.get("GLYX_API_URL", "https://glyx.ai")
        self.supabase: AsyncClient | None = None
        self.supabase_sync: Client | None = None  # For polling
        self.executor = TaskExecutor(self.api_base_url)
        self.running = False
        self.task_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.start_time = time.time()

    async def _create_supabase_client(self) -> AsyncClient:
        """Create async Supabase client for Realtime."""
        url = settings.supabase_url
        key = settings.supabase_service_role_key or settings.supabase_anon_key

        if not url or not key:
            raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY/SUPABASE_ANON_KEY")

        return await create_async_client(url, key)

    def _create_sync_client(self) -> Client:
        """Create sync Supabase client for polling."""
        url = settings.supabase_url
        key = settings.supabase_service_role_key or settings.supabase_anon_key
        return create_client(url, key)

    def _on_task_insert(self, payload: dict[str, Any]) -> None:
        """Handle new task insertion from Realtime."""
        new_task = payload.get("new", {})
        if not new_task:
            return

        task_id = new_task.get("id")
        task_device_id = new_task.get("device_id")
        task_status = new_task.get("status")

        # Only process tasks for this device that are pending
        if task_device_id != self.device_id:
            logger.debug(f"Ignoring task {task_id} for device {task_device_id}")
            return

        if task_status != "pending":
            logger.debug(f"Ignoring task {task_id} with status {task_status}")
            return

        logger.info(f"Received new task: {task_id}")

        # Queue the task for execution
        try:
            self.task_queue.put_nowait(new_task)
        except asyncio.QueueFull:
            logger.error(f"Task queue full, dropping task {task_id}")

    async def _process_tasks(self) -> None:
        """Worker that processes tasks from the queue."""
        while self.running:
            try:
                task = await asyncio.wait_for(
                    self.task_queue.get(),
                    timeout=1.0,
                )
                # Execute in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    self.executor.execute_task,
                    task,
                )
                self.task_queue.task_done()
            except TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing task: {e}")

    async def _send_heartbeat(self) -> bool:
        """Send a heartbeat to the server to indicate daemon is alive."""
        url = f"{self.api_base_url}/api/devices/{self.device_id}/heartbeat"
        uptime = time.time() - self.start_time

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    json={
                        "uptime_seconds": uptime,
                        "hostname": _get_hostname(),
                        "version": "1.0.0",
                    },
                )
                response.raise_for_status()
                logger.debug(f"Heartbeat sent successfully (uptime: {uptime:.0f}s)")
                return True
        except Exception as e:
            logger.warning(f"Failed to send heartbeat: {e}")
            return False

    async def _heartbeat_loop(self) -> None:
        """Periodically send heartbeats to the server."""
        while self.running:
            await self._send_heartbeat()
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)

    def _poll_pending_tasks(self) -> None:
        """Poll for any pending tasks that might have been missed."""
        try:
            result = (
                self.supabase_sync.table("agent_tasks")
                .select("*")
                .eq("device_id", self.device_id)
                .eq("status", "pending")
                .execute()
            )

            if result.data:
                logger.info(f"Found {len(result.data)} pending tasks")
                for task in result.data:
                    try:
                        self.task_queue.put_nowait(task)
                    except asyncio.QueueFull:
                        logger.warning("Task queue full during poll")
                        break
        except Exception as e:
            logger.error(f"Error polling pending tasks: {e}")

    async def subscribe_to_tasks(self) -> Any:
        """Subscribe to Realtime for task insertions."""
        channel_name = f"daemon-{self.device_id}"
        channel = self.supabase.channel(channel_name)

        # Subscribe to INSERT events on agent_tasks
        channel.on_postgres_changes(
            event="INSERT",
            schema="public",
            table="agent_tasks",
            callback=self._on_task_insert,
        )

        await channel.subscribe()
        logger.info(f"Subscribed to Realtime channel: {channel_name}")
        return channel

    async def run(self) -> None:
        """Run the daemon."""
        logger.info(f"Starting Glyx Daemon for device: {self.device_id}")
        logger.info(f"API base URL: {self.api_base_url}")

        self.supabase = await self._create_supabase_client()
        self.supabase_sync = self._create_sync_client()
        self.running = True

        # Subscribe to Realtime (channel kept alive by reference)
        self._channel = await self.subscribe_to_tasks()

        # Small delay to ensure subscription is active
        await asyncio.sleep(1.0)

        # Send initial heartbeat
        await self._send_heartbeat()

        # Poll for any existing pending tasks
        self._poll_pending_tasks()

        # Start task processor and heartbeat loop
        processor_task = asyncio.create_task(self._process_tasks())
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info("Daemon is running. Press Ctrl+C to stop.")

        try:
            # Keep running until interrupted
            while self.running:
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass
        finally:
            self.running = False
            processor_task.cancel()
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await processor_task
                await heartbeat_task
            logger.info("Daemon stopped.")

    def stop(self) -> None:
        """Stop the daemon."""
        self.running = False


def _get_hostname() -> str:
    """Get the local hostname."""
    import socket

    return socket.gethostname()


def _register_device(user_id: str) -> str | None:
    """Register this machine as a device for the given user."""
    import uuid

    url = settings.supabase_url
    key = settings.supabase_service_role_key or settings.supabase_anon_key

    if not url or not key:
        logger.error("Missing Supabase credentials for device registration")
        return None

    supabase = create_client(url, key)
    hostname = _get_hostname()

    # Check if device already exists for this user/hostname
    try:
        existing = (
            supabase.table("paired_devices")
            .select("id")
            .eq("user_id", user_id)
            .eq("hostname", hostname)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.error(f"Error checking for existing device: {e}")
        existing = None

    if existing and existing.data:
        device_id = existing.data[0]["id"]
        logger.info(f"Found existing device: {device_id}")
        return device_id

    # Create new device
    device_id = str(uuid.uuid4())
    device_data = {
        "id": device_id,
        "user_id": user_id,
        "name": f"Daemon on {hostname}",
        "hostname": hostname,
        "status": "active",
        "relay_url": "local://daemon",  # Daemon doesn't use relay, executes locally
    }

    result = supabase.table("paired_devices").insert(device_data).execute()

    if result.data:
        logger.info(f"Registered new device: {device_id}")
        return device_id
    else:
        logger.error("Failed to register device")
        return None


def _load_device_id_from_file() -> str | None:
    """Load device ID from ~/.glyx/device_id (created by glyx-pair script)."""
    device_id_file = os.path.expanduser("~/.glyx/device_id")
    try:
        if os.path.exists(device_id_file):
            with open(device_id_file) as f:
                device_id = f.read().strip()
                if device_id:
                    return device_id
    except Exception as e:
        logger.debug(f"Could not read device ID from file: {e}")
    return None


def main() -> int:
    """Entry point for glyx-daemon CLI."""
    parser = argparse.ArgumentParser(
        description="Glyx Daemon - Local task executor for iOS orchestration",
    )
    parser.add_argument(
        "--device-id",
        default=os.environ.get("GLYX_DEVICE_ID"),
        help="Device ID to listen for tasks (default: ~/.glyx/device_id or GLYX_DEVICE_ID env var)",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("GLYX_API_URL", "https://glyx.ai"),
        help="API base URL (default: https://glyx.ai)",
    )
    parser.add_argument(
        "--register",
        metavar="USER_ID",
        help="Auto-register this machine as a device for the given user ID",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    device_id = args.device_id

    # Try loading from ~/.glyx/device_id if not provided
    if not device_id:
        device_id = _load_device_id_from_file()
        if device_id:
            logger.info(f"Loaded device ID from ~/.glyx/device_id: {device_id}")

    # Handle auto-registration (deprecated - use glyx-pair instead)
    if args.register:
        device_id = _register_device(args.register)
        if not device_id:
            print("Error: Failed to register device", file=sys.stderr)
            return 1
        print(f"Device registered: {device_id}")
        print(f"You can also set: GLYX_DEVICE_ID={device_id}")

    if not device_id:
        print(
            "Error: No device ID found.",
            file=sys.stderr,
        )
        print(
            "\nTo pair this device:",
            file=sys.stderr,
        )
        print(
            "  1. Run 'glyx-pair' to generate a QR code",
            file=sys.stderr,
        )
        print(
            "  2. Scan the QR code with the Glyx iOS app",
            file=sys.stderr,
        )
        print(
            "  3. Run 'glyx-daemon' again",
            file=sys.stderr,
        )
        print(
            "\nOr set GLYX_DEVICE_ID environment variable manually.",
            file=sys.stderr,
        )
        return 1

    daemon = GlyxDaemon(
        device_id=device_id,
        api_base_url=args.api_url,
    )

    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        daemon.stop()
        print("\nDaemon stopped by user.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

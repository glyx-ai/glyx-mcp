#!/usr/bin/env python3
"""Push notification testing CLI tool.

Tests the Knock notification workflows end-to-end.

Usage:
    # Send a test HITL notification (needs input)
    uv run scripts/test_notifications.py hitl --prompt "Deploy to prod?"

    # Send agent start notification
    uv run scripts/test_notifications.py agent-start --summary "Building feature X"

    # Send agent completed notification
    uv run scripts/test_notifications.py agent-completed --summary "Feature X built" --time 45.2

    # Send agent error notification
    uv run scripts/test_notifications.py agent-error --summary "Build failed" --error "Timeout"

    # List Knock workflows (requires KNOCK_API_KEY)
    uv run scripts/test_notifications.py list-workflows
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from dataclasses import dataclass

from dotenv import load_dotenv
from knockapi import Knock
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()

console = Console()


@dataclass
class NotificationConfig:
    """Configuration for notification testing."""

    knock_api_key: str
    default_user_id: str | None = None

    @classmethod
    def from_env(cls) -> "NotificationConfig":
        """Load config from environment."""
        knock_key = os.getenv("KNOCK_API_KEY", "")

        if not knock_key:
            console.print("[red]Error: KNOCK_API_KEY not set[/red]")
            sys.exit(1)

        return cls(knock_api_key=knock_key)


class NotificationTester:
    """Test Knock notification workflows."""

    WORKFLOWS = {
        "agent-needs-input": "Agent needs human input (HITL)",
        "agent-start": "Agent task started",
        "agent-completed": "Agent task completed",
        "agent-error": "Agent task failed",
    }

    def __init__(self, config: NotificationConfig) -> None:
        self.config = config
        self.knock = Knock(api_key=config.knock_api_key)

    async def get_user_id(self, user_id: str | None) -> str:
        """Get user ID from arg or try to detect from Supabase."""
        if user_id:
            return user_id

        # Try to get from Supabase
        import httpx

        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

        if supabase_url and supabase_key:
            async with httpx.AsyncClient() as client:
                try:
                    # Try profiles table first
                    response = await client.get(
                        f"{supabase_url}/rest/v1/profiles",
                        headers={
                            "apikey": supabase_key,
                            "Authorization": f"Bearer {supabase_key}",
                        },
                        params={"limit": "1"},
                    )
                    if response.status_code == 200 and response.json():
                        return response.json()[0]["id"]
                except Exception:
                    pass

        console.print("[yellow]Could not auto-detect user. Using test UUID.[/yellow]")
        return str(uuid.uuid4())

    def trigger_workflow(
        self,
        workflow_key: str,
        user_id: str,
        data: dict,
    ) -> dict:
        """Trigger a Knock workflow."""
        console.print(f"[dim]Triggering workflow: {workflow_key}[/dim]")

        result = self.knock.workflows.trigger(
            key=workflow_key,
            recipients=[user_id],
            data=data,
        )

        return result

    def send_hitl_notification(
        self,
        user_id: str,
        prompt: str,
        task_id: str | None = None,
        hitl_request_id: str | None = None,
        agent_type: str = "claude",
        device_name: str | None = None,
    ) -> dict:
        """Send HITL (needs input) notification."""
        task_id = task_id or str(uuid.uuid4())
        hitl_request_id = hitl_request_id or str(uuid.uuid4())

        data = {
            "event_type": "needs_input",
            "agent_type": agent_type,
            "session_id": task_id,
            "task_summary": prompt[:200],
            "urgency": "critical",
            "action_required": True,
            "hitl_request_id": hitl_request_id,
        }
        if device_name:
            data["device_name"] = device_name

        return self.trigger_workflow("agent-needs-input", user_id, data)

    def send_agent_start(
        self,
        user_id: str,
        task_summary: str,
        task_id: str | None = None,
        agent_type: str = "claude",
        device_name: str | None = None,
    ) -> dict:
        """Send agent start notification."""
        task_id = task_id or str(uuid.uuid4())

        data = {
            "event_type": "started",
            "agent_type": agent_type,
            "session_id": task_id,
            "task_summary": task_summary[:200],
            "urgency": "medium",
            "action_required": False,
        }
        if device_name:
            data["device_name"] = device_name

        return self.trigger_workflow("agent-start", user_id, data)

    def send_agent_completed(
        self,
        user_id: str,
        task_summary: str,
        execution_time_s: float | None = None,
        task_id: str | None = None,
        agent_type: str = "claude",
        device_name: str | None = None,
    ) -> dict:
        """Send agent completed notification."""
        task_id = task_id or str(uuid.uuid4())

        data = {
            "event_type": "completed",
            "agent_type": agent_type,
            "session_id": task_id,
            "task_summary": task_summary[:200],
            "urgency": "low",
            "action_required": False,
        }
        if device_name:
            data["device_name"] = device_name
        if execution_time_s is not None:
            data["execution_time_s"] = execution_time_s

        return self.trigger_workflow("agent-completed", user_id, data)

    def send_agent_error(
        self,
        user_id: str,
        task_summary: str,
        error_message: str,
        task_id: str | None = None,
        agent_type: str = "claude",
        device_name: str | None = None,
    ) -> dict:
        """Send agent error notification."""
        task_id = task_id or str(uuid.uuid4())

        data = {
            "event_type": "error",
            "agent_type": agent_type,
            "session_id": task_id,
            "task_summary": task_summary[:200],
            "error_message": error_message[:500],
            "urgency": "high",
            "action_required": True,
        }
        if device_name:
            data["device_name"] = device_name

        return self.trigger_workflow("agent-error", user_id, data)


async def cmd_hitl(args: argparse.Namespace, tester: NotificationTester) -> None:
    """Send HITL notification."""
    user_id = await tester.get_user_id(args.user_id)
    hitl_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())

    result = tester.send_hitl_notification(
        user_id=user_id,
        prompt=args.prompt,
        task_id=task_id,
        hitl_request_id=hitl_id,
        agent_type=args.agent_type,
        device_name=args.device_name,
    )

    console.print(
        Panel(
            f"[green]HITL notification sent![/green]\n\n"
            f"User ID: [cyan]{user_id}[/cyan]\n"
            f"Task ID: [cyan]{task_id}[/cyan]\n"
            f"HITL ID: [cyan]{hitl_id}[/cyan]\n"
            f"Prompt: {args.prompt}\n\n"
            f"Workflow: agent-needs-input\n"
            f"Result: {result}",
            title="HITL Notification",
        )
    )


async def cmd_agent_start(args: argparse.Namespace, tester: NotificationTester) -> None:
    """Send agent start notification."""
    user_id = await tester.get_user_id(args.user_id)
    task_id = str(uuid.uuid4())

    result = tester.send_agent_start(
        user_id=user_id,
        task_summary=args.summary,
        task_id=task_id,
        agent_type=args.agent_type,
        device_name=args.device_name,
    )

    console.print(
        Panel(
            f"[green]Agent start notification sent![/green]\n\n"
            f"User ID: [cyan]{user_id}[/cyan]\n"
            f"Task ID: [cyan]{task_id}[/cyan]\n"
            f"Summary: {args.summary}\n\n"
            f"Result: {result}",
            title="Agent Start Notification",
        )
    )


async def cmd_agent_completed(args: argparse.Namespace, tester: NotificationTester) -> None:
    """Send agent completed notification."""
    user_id = await tester.get_user_id(args.user_id)
    task_id = str(uuid.uuid4())

    result = tester.send_agent_completed(
        user_id=user_id,
        task_summary=args.summary,
        execution_time_s=args.time,
        task_id=task_id,
        agent_type=args.agent_type,
        device_name=args.device_name,
    )

    console.print(
        Panel(
            f"[green]Agent completed notification sent![/green]\n\n"
            f"User ID: [cyan]{user_id}[/cyan]\n"
            f"Task ID: [cyan]{task_id}[/cyan]\n"
            f"Summary: {args.summary}\n"
            f"Time: {args.time}s\n\n"
            f"Result: {result}",
            title="Agent Completed Notification",
        )
    )


async def cmd_agent_error(args: argparse.Namespace, tester: NotificationTester) -> None:
    """Send agent error notification."""
    user_id = await tester.get_user_id(args.user_id)
    task_id = str(uuid.uuid4())

    result = tester.send_agent_error(
        user_id=user_id,
        task_summary=args.summary,
        error_message=args.error,
        task_id=task_id,
        agent_type=args.agent_type,
        device_name=args.device_name,
    )

    console.print(
        Panel(
            f"[yellow]Agent error notification sent![/yellow]\n\n"
            f"User ID: [cyan]{user_id}[/cyan]\n"
            f"Task ID: [cyan]{task_id}[/cyan]\n"
            f"Summary: {args.summary}\n"
            f"Error: {args.error}\n\n"
            f"Result: {result}",
            title="Agent Error Notification",
        )
    )


async def cmd_list_workflows(args: argparse.Namespace, tester: NotificationTester) -> None:
    """List available Knock workflows."""
    table = Table(title="Knock Workflows")
    table.add_column("Workflow Key", style="cyan")
    table.add_column("Description")
    table.add_column("Status", style="green")

    for key, description in NotificationTester.WORKFLOWS.items():
        table.add_row(key, description, "configured")

    console.print(table)
    console.print(
        "\n[dim]These workflows should be configured in the Knock dashboard.[/dim]"
    )


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Push notification testing CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Common args
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("--user-id", "-u", help="User ID (auto-detects if not set)")
    common_parser.add_argument("--agent-type", "-a", default="claude", help="Agent type")
    common_parser.add_argument("--device-name", "-d", help="Device name")

    # HITL command
    hitl_parser = subparsers.add_parser(
        "hitl", parents=[common_parser], help="Send HITL notification"
    )
    hitl_parser.add_argument("--prompt", "-p", required=True, help="HITL prompt text")

    # Agent start command
    start_parser = subparsers.add_parser(
        "agent-start", parents=[common_parser], help="Send agent start notification"
    )
    start_parser.add_argument("--summary", "-s", required=True, help="Task summary")

    # Agent completed command
    completed_parser = subparsers.add_parser(
        "agent-completed", parents=[common_parser], help="Send agent completed notification"
    )
    completed_parser.add_argument("--summary", "-s", required=True, help="Task summary")
    completed_parser.add_argument("--time", "-t", type=float, help="Execution time in seconds")

    # Agent error command
    error_parser = subparsers.add_parser(
        "agent-error", parents=[common_parser], help="Send agent error notification"
    )
    error_parser.add_argument("--summary", "-s", required=True, help="Task summary")
    error_parser.add_argument("--error", "-e", required=True, help="Error message")

    # List workflows command
    subparsers.add_parser("list-workflows", help="List available Knock workflows")

    args = parser.parse_args()

    config = NotificationConfig.from_env()
    tester = NotificationTester(config)

    try:
        if args.command == "hitl":
            await cmd_hitl(args, tester)
        elif args.command == "agent-start":
            await cmd_agent_start(args, tester)
        elif args.command == "agent-completed":
            await cmd_agent_completed(args, tester)
        elif args.command == "agent-error":
            await cmd_agent_error(args, tester)
        elif args.command == "list-workflows":
            await cmd_list_workflows(args, tester)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

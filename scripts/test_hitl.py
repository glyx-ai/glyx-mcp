#!/usr/bin/env python3
"""HITL testing CLI tool.

Usage:
    # Create a test task and HITL request (triggers push notification)
    uv run scripts/test_hitl.py create --prompt "Should I deploy to production?"

    # List pending HITL requests for a user
    uv run scripts/test_hitl.py list

    # Respond to an HITL request
    uv run scripts/test_hitl.py respond <hitl_id> --response "Yes"

    # Check expiration status
    uv run scripts/test_hitl.py check-expirations

    # Full end-to-end test
    uv run scripts/test_hitl.py e2e
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()

console = Console()


@dataclass
class Config:
    """Configuration for HITL testing."""

    api_base_url: str
    supabase_url: str
    supabase_key: str
    default_user_id: str | None = None
    default_device_id: str | None = None

    @classmethod
    def from_env(cls) -> "Config":
        """Load config from environment variables."""
        api_url = os.getenv(
            "GLYX_API_URL",
            "https://glyx-mcp-996426597393.us-central1.run.app",
        )
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

        if not supabase_url or not supabase_key:
            console.print(
                "[yellow]Warning: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set. "
                "Some features may not work.[/yellow]"
            )

        return cls(
            api_base_url=api_url,
            supabase_url=supabase_url,
            supabase_key=supabase_key,
        )


class HITLTestClient:
    """Client for testing HITL functionality."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    async def get_first_user(self) -> dict[str, Any] | None:
        """Get the first user from Supabase auth.users."""
        if not self.config.supabase_url or not self.config.supabase_key:
            return None

        try:
            response = await self.client.get(
                f"{self.config.supabase_url}/rest/v1/rpc/get_auth_users",
                headers={
                    "apikey": self.config.supabase_key,
                    "Authorization": f"Bearer {self.config.supabase_key}",
                },
            )
            if response.status_code == 200:
                users = response.json()
                if users:
                    return users[0]
        except Exception:
            pass

        # Fallback: query auth.users directly via PostgREST
        try:
            response = await self.client.post(
                f"{self.config.supabase_url}/rest/v1/rpc",
                headers={
                    "apikey": self.config.supabase_key,
                    "Authorization": f"Bearer {self.config.supabase_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "query": "SELECT id, email FROM auth.users LIMIT 1",
                },
            )
            if response.status_code == 200:
                result = response.json()
                if result:
                    return result[0]
        except Exception:
            pass

        return None

    async def create_task(
        self,
        user_id: str,
        device_id: str,
        prompt: str,
        agent_type: str = "claude",
    ) -> dict[str, Any]:
        """Create a test agent task."""
        task_id = str(uuid.uuid4())

        # Insert directly via Supabase
        response = await self.client.post(
            f"{self.config.supabase_url}/rest/v1/agent_tasks",
            headers={
                "apikey": self.config.supabase_key,
                "Authorization": f"Bearer {self.config.supabase_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json={
                "id": task_id,
                "user_id": user_id,
                "device_id": device_id,
                "agent_type": agent_type,
                "task_type": "chat",
                "payload": {"prompt": prompt},
                "status": "running",
            },
        )

        if response.status_code not in (200, 201):
            raise Exception(f"Failed to create task: {response.status_code} - {response.text}")

        return response.json()[0]

    async def create_hitl_request(
        self,
        task_id: str,
        prompt: str,
        options: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create an HITL request (triggers push notification)."""
        response = await self.client.post(
            f"{self.config.api_base_url}/api/hitl",
            json={
                "task_id": task_id,
                "prompt": prompt,
                "options": options,
            },
        )

        if response.status_code != 200:
            raise Exception(f"Failed to create HITL request: {response.status_code} - {response.text}")

        return response.json()

    async def list_pending_requests(self, user_id: str) -> list[dict[str, Any]]:
        """List pending HITL requests for a user."""
        response = await self.client.get(
            f"{self.config.api_base_url}/api/hitl/pending",
            params={"user_id": user_id},
        )

        if response.status_code != 200:
            raise Exception(f"Failed to list requests: {response.status_code} - {response.text}")

        return response.json()

    async def get_hitl_request(self, hitl_id: str) -> dict[str, Any]:
        """Get a specific HITL request."""
        response = await self.client.get(
            f"{self.config.api_base_url}/api/hitl/{hitl_id}",
        )

        if response.status_code != 200:
            raise Exception(f"Failed to get request: {response.status_code} - {response.text}")

        return response.json()

    async def respond_to_hitl(self, hitl_id: str, response_text: str) -> dict[str, Any]:
        """Respond to an HITL request."""
        response = await self.client.post(
            f"{self.config.api_base_url}/api/hitl/{hitl_id}/respond",
            json={"response": response_text},
        )

        if response.status_code != 200:
            raise Exception(f"Failed to respond: {response.status_code} - {response.text}")

        return response.json()

    async def check_expirations(self) -> dict[str, Any]:
        """Check and mark expired HITL requests."""
        response = await self.client.post(
            f"{self.config.api_base_url}/api/hitl/expiration-check",
        )

        if response.status_code != 200:
            raise Exception(f"Failed to check expirations: {response.status_code} - {response.text}")

        return response.json()


async def cmd_create(args: argparse.Namespace, client: HITLTestClient) -> None:
    """Create a test task and HITL request."""
    user_id = args.user_id
    device_id = args.device_id or "test-device-" + str(uuid.uuid4())[:8]

    # Auto-detect user if not provided
    if not user_id:
        console.print("[dim]Auto-detecting user...[/dim]")
        user = await client.get_first_user()
        if user:
            user_id = user.get("id")
            console.print(f"[green]Found user: {user.get('email', user_id)}[/green]")
        else:
            console.print("[red]No user found. Please specify --user-id[/red]")
            return

    # Create task
    console.print(f"\n[bold]Creating task...[/bold]")
    task = await client.create_task(
        user_id=user_id,
        device_id=device_id,
        prompt=args.prompt,
        agent_type=args.agent_type,
    )
    console.print(f"  Task ID: [cyan]{task['id']}[/cyan]")

    # Create HITL request
    console.print(f"\n[bold]Creating HITL request...[/bold]")
    options = args.options.split(",") if args.options else None
    hitl = await client.create_hitl_request(
        task_id=task["id"],
        prompt=args.prompt,
        options=options,
    )

    console.print(
        Panel(
            f"[green]HITL request created![/green]\n\n"
            f"Task ID: [cyan]{task['id']}[/cyan]\n"
            f"HITL ID: [cyan]{hitl['id']}[/cyan]\n"
            f"Prompt: {hitl['prompt']}\n"
            f"Expires: {hitl['expires_at']}\n\n"
            f"[yellow]Push notification sent to user {user_id}[/yellow]",
            title="Test HITL Created",
        )
    )


async def cmd_list(args: argparse.Namespace, client: HITLTestClient) -> None:
    """List pending HITL requests."""
    user_id = args.user_id

    if not user_id:
        user = await client.get_first_user()
        if user:
            user_id = user.get("id")
        else:
            console.print("[red]No user found. Please specify --user-id[/red]")
            return

    requests = await client.list_pending_requests(user_id)

    if not requests:
        console.print("[yellow]No pending HITL requests[/yellow]")
        return

    table = Table(title="Pending HITL Requests")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Prompt", max_width=40)
    table.add_column("Status", style="green")
    table.add_column("Expires", style="yellow")

    for req in requests:
        expires_at = datetime.fromisoformat(req["expires_at"].replace("Z", "+00:00"))
        remaining = int((expires_at - datetime.now(UTC)).total_seconds())
        expires_str = f"{remaining}s" if remaining > 0 else "EXPIRED"

        table.add_row(
            req["id"][:8] + "...",
            req["prompt"][:40],
            req["status"],
            expires_str,
        )

    console.print(table)


async def cmd_respond(args: argparse.Namespace, client: HITLTestClient) -> None:
    """Respond to an HITL request."""
    result = await client.respond_to_hitl(args.hitl_id, args.response)

    console.print(
        Panel(
            f"[green]Response submitted![/green]\n\n"
            f"HITL ID: [cyan]{result['id']}[/cyan]\n"
            f"Response: {result['response']}\n"
            f"Status: {result['status']}\n"
            f"Responded at: {result['responded_at']}",
            title="HITL Response",
        )
    )


async def cmd_check_expirations(args: argparse.Namespace, client: HITLTestClient) -> None:
    """Check and mark expired HITL requests."""
    result = await client.check_expirations()

    if result["expired_count"] == 0:
        console.print("[green]No expired HITL requests[/green]")
    else:
        console.print(
            Panel(
                f"[yellow]Expired {result['expired_count']} HITL request(s)[/yellow]\n\n"
                f"HITL IDs: {', '.join(result['hitl_ids'])}\n"
                f"Task IDs: {', '.join(result['task_ids'])}",
                title="Expiration Check",
            )
        )


async def cmd_e2e(args: argparse.Namespace, client: HITLTestClient) -> None:
    """Run full end-to-end HITL test."""
    console.print("[bold]Running end-to-end HITL test...[/bold]\n")

    # Get user
    user = await client.get_first_user()
    if not user:
        console.print("[red]No user found in database[/red]")
        return
    user_id = user.get("id")
    console.print(f"[green]1.[/green] Found user: {user.get('email', user_id)}")

    # Create task
    device_id = f"e2e-test-{uuid.uuid4().hex[:8]}"
    task = await client.create_task(
        user_id=user_id,
        device_id=device_id,
        prompt="E2E test: Approve this request?",
        agent_type="claude",
    )
    console.print(f"[green]2.[/green] Created task: {task['id'][:8]}...")

    # Create HITL request
    hitl = await client.create_hitl_request(
        task_id=task["id"],
        prompt="E2E test: Approve this request?",
        options=["Yes", "No"],
    )
    console.print(f"[green]3.[/green] Created HITL request: {hitl['id'][:8]}...")
    console.print(f"   [yellow]Push notification sent![/yellow]")

    # Verify pending
    pending = await client.list_pending_requests(user_id)
    found = any(r["id"] == hitl["id"] for r in pending)
    console.print(f"[green]4.[/green] Verified in pending list: {found}")

    # Respond
    if args.auto_respond:
        await asyncio.sleep(1)
        result = await client.respond_to_hitl(hitl["id"], "Yes")
        console.print(f"[green]5.[/green] Auto-responded: {result['status']}")

        # Verify not pending anymore
        pending = await client.list_pending_requests(user_id)
        found = any(r["id"] == hitl["id"] for r in pending)
        console.print(f"[green]6.[/green] Removed from pending: {not found}")

    console.print("\n[bold green]E2E test completed![/bold green]")


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="HITL testing CLI tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Create command
    create_parser = subparsers.add_parser("create", help="Create test task + HITL request")
    create_parser.add_argument("--prompt", "-p", required=True, help="HITL prompt text")
    create_parser.add_argument("--user-id", "-u", help="User ID (auto-detects if not set)")
    create_parser.add_argument("--device-id", "-d", help="Device ID (generates if not set)")
    create_parser.add_argument("--agent-type", "-a", default="claude", help="Agent type")
    create_parser.add_argument("--options", "-o", help="Comma-separated options (e.g., 'Yes,No')")

    # List command
    list_parser = subparsers.add_parser("list", help="List pending HITL requests")
    list_parser.add_argument("--user-id", "-u", help="User ID (auto-detects if not set)")

    # Respond command
    respond_parser = subparsers.add_parser("respond", help="Respond to HITL request")
    respond_parser.add_argument("hitl_id", help="HITL request ID")
    respond_parser.add_argument("--response", "-r", required=True, help="Response text")

    # Check expirations command
    subparsers.add_parser("check-expirations", help="Check and mark expired requests")

    # E2E command
    e2e_parser = subparsers.add_parser("e2e", help="Run full end-to-end test")
    e2e_parser.add_argument("--auto-respond", action="store_true", help="Auto-respond to request")

    args = parser.parse_args()

    config = Config.from_env()
    client = HITLTestClient(config)

    try:
        if args.command == "create":
            await cmd_create(args, client)
        elif args.command == "list":
            await cmd_list(args, client)
        elif args.command == "respond":
            await cmd_respond(args, client)
        elif args.command == "check-expirations":
            await cmd_check_expirations(args, client)
        elif args.command == "e2e":
            await cmd_e2e(args, client)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())

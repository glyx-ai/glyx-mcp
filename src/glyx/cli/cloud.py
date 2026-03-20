"""Cloud agent setup — transfers Claude Code token to Glyx iOS via pairing code."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path

import httpx
import typer
from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

BRAND = "bright_magenta"
ACCENT = "cyan"
DIM = "dim"

SUPA_URL = os.environ.get("SUPABASE_URL", "https://vpopliwokdmpxhmippwc.supabase.co")
SUPA_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "sb_publishable_PFYg1B15pdweWFaL6BRDCQ_SnX-BbZf",
)

PAIRING_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

LOGO = "\n".join([
    "   ██████╗ ██╗  ██╗   ██╗██╗  ██╗",
    "  ██╔════╝ ██║  ╚██╗ ██╔╝╚██╗██╔╝",
    "  ██║  ███╗██║   ╚████╔╝  ╚███╔╝ ",
    "  ██║   ██║██║    ╚██╔╝   ██╔██╗ ",
    "  ╚██████╔╝██████╗ ██║   ██╔╝ ██╗",
    "   ╚═════╝ ╚═════╝ ╚═╝   ╚═╝  ╚═╝",
])

console = Console(force_terminal=True)
app = typer.Typer(add_completion=False)


def claude_code_token() -> str | None:
    creds = Path.home() / ".claude" / ".credentials.json"
    if not creds.exists():
        return None
    try:
        oauth = json.loads(creds.read_text()).get("claudeAiOauth", {})
        return oauth.get("accessToken") or None
    except Exception:
        return None


def generate_code() -> str:
    return "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(6))


def store_code(code: str, token: str, retries: int = 3) -> str:
    url = f"{SUPA_URL}/rest/v1/pairing_codes"
    headers = {
        "apikey": SUPA_KEY,
        "Authorization": f"Bearer {SUPA_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    row = {"code": code, "payload": "glyx://cloud-setup", "claude_token": token}

    for attempt in range(retries):
        resp = httpx.post(url, json=row, headers=headers)
        if resp.status_code == 201:
            return code
        if resp.status_code == 409 and attempt < retries - 1:
            code = generate_code()
            row["code"] = code
            continue
        resp.raise_for_status()

    return code


@app.callback(invoke_without_command=True)
def cloud() -> None:
    """Set up your Cloud Agent with Claude Code."""
    console.clear()
    console.print()
    console.print(Align.center(Text(LOGO, style=f"bold {BRAND}")))
    console.print()
    console.print(Align.center(Text("Cloud Agent Setup", style=f"bold {ACCENT}")))
    console.print()

    # Check for Claude Code
    if not shutil.which("claude"):
        console.print(f"  [bold red]✗[/]  Claude Code not found")
        console.print(f"  [{DIM}]Install it: https://docs.anthropic.com/en/docs/claude-code[/]")
        raise typer.Exit(1)

    console.print(f"  [bold {ACCENT}]✓[/]  Claude Code found")

    # Check for token
    token = claude_code_token()
    if not token:
        console.print(f"  [{DIM}]Not authenticated — launching login...[/]")
        console.print()
        try:
            result = subprocess.run(["claude", "auth", "login"], timeout=120)
            if result.returncode != 0:
                console.print(f"  [bold red]✗[/]  Authentication failed")
                raise typer.Exit(1)
        except (subprocess.TimeoutExpired, Exception):
            console.print(f"  [bold red]✗[/]  Authentication timed out")
            raise typer.Exit(1)

        token = claude_code_token()
        if not token:
            console.print(f"  [bold red]✗[/]  No token found after login")
            raise typer.Exit(1)

    console.print(f"  [bold {ACCENT}]✓[/]  Claude Code authenticated")

    # Generate and store code
    code = generate_code()
    try:
        code = store_code(code, token)
    except Exception as exc:
        console.print(f"  [bold red]✗[/]  Failed to generate code: {exc}")
        raise typer.Exit(1)

    console.print(f"  [bold {ACCENT}]✓[/]  Code generated")
    console.print()

    # Display the code
    spaced = "  ".join(code[:3]) + "  -  " + "  ".join(code[3:])
    console.print(Panel(
        Align.center(Text(spaced, style=f"bold {ACCENT}")),
        title=f"[bold {BRAND}] Enter this code in the Glyx app [/]",
        subtitle=f"[{DIM}]Cloud Agent → Setup Cloud Agent[/{DIM}]",
        box=box.ROUNDED,
        border_style=BRAND,
        padding=(1, 4),
    ))
    console.print()
    console.print(Align.center(Text("Code expires in 10 minutes", style=DIM)))
    console.print()

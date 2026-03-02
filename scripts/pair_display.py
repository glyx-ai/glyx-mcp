#!/usr/bin/env python3
"""Pairing display — QR code + MCP server startup."""

from __future__ import annotations

import io
import json
import os
import platform
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import segno
from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# ── Brand ────────────────────────────────────────────────────

BRAND = "bright_magenta"
ACCENT = "cyan"
DIM = "dim"

GLYX_DIR = Path.home() / ".glyx"
DEVICE_ID_FILE = GLYX_DIR / "device_id"
SERVER_PORT = 8000

console = Console(force_terminal=True)


# ── Environment detection ────────────────────────────────────


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def device_id() -> str:
    if DEVICE_ID_FILE.exists():
        return DEVICE_ID_FILE.read_text().strip()
    did = str(uuid.uuid4())
    GLYX_DIR.mkdir(parents=True, exist_ok=True)
    DEVICE_ID_FILE.write_text(did)
    return did


def installed_agents() -> list[str]:
    return [a for a in ("claude", "cursor", "codex", "aider") if shutil.which(a)]


def claude_code_token() -> str | None:
    creds = Path.home() / ".claude" / ".credentials.json"
    if not creds.exists():
        return None
    try:
        oauth = json.loads(creds.read_text()).get("claudeAiOauth", {})
        return oauth.get("accessToken") or None
    except Exception:
        return None


def offer_claude_auth() -> bool:
    """Prompt user to authenticate Claude Code if installed but not authed."""
    if not shutil.which("claude"):
        return False
    if claude_code_token():
        return True

    console.print()
    console.print(f"  [{ACCENT}]Claude Code[/] detected but not authenticated.", highlight=False)
    console.print(f"  [{DIM}]Sign in to enable Cloud Agent — run agents from anywhere.[/]", highlight=False)
    console.print()

    try:
        answer = console.input(f"  [{BRAND}]Run `claude auth login` now?[/] [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False

    if answer and answer not in ("y", "yes"):
        return False

    console.print()
    console.print(f"  [{DIM}]Opening browser for authentication...[/]")
    console.print()

    try:
        result = subprocess.run(["claude", "auth", "login"], timeout=120)
        if result.returncode != 0:
            console.print(f"  [{DIM}]Authentication failed — skipping cloud setup.[/]")
            return False
    except (subprocess.TimeoutExpired, Exception):
        console.print(f"  [{DIM}]Authentication timed out — skipping cloud setup.[/]")
        return False

    if claude_code_token():
        console.print(f"  [bold {ACCENT}]✓[/] Claude Code authenticated")
        return True

    console.print(f"  [{DIM}]No token found after login — skipping cloud setup.[/]")
    return False


# ── Port management ──────────────────────────────────────────


def free_port(port: int) -> None:
    """Ensure the given port is available by stopping any process using it."""
    result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
    pids = [p for p in result.stdout.strip().split("\n") if p]
    for pid in pids:
        subprocess.run(["kill", "-9", pid], capture_output=True)


# ── QR payload ───────────────────────────────────────────────


def qr_payload(env: dict) -> str:
    parts = [
        f"glyx://pair?device_id={env['device_id']}",
        f"&host={env['hostname']}",
        f"&user={env['username']}",
        f"&name={env['hostname']}",
        f"&ip={env['ip']}",
        f"&server_port={env['port']}",
    ]
    if env["agents"]:
        parts.append(f"&agents={','.join(env['agents'])}")
    if env.get("has_claude_token"):
        parts.append("&has_claude_token=1")
    return "".join(parts)


# ── Rich renderables ─────────────────────────────────────────


LOGO = "\n".join([
    "   ██████╗ ██╗  ██╗   ██╗██╗  ██╗",
    "  ██╔════╝ ██║  ╚██╗ ██╔╝╚██╗██╔╝",
    "  ██║  ███╗██║   ╚████╔╝  ╚███╔╝ ",
    "  ██║   ██║██║    ╚██╔╝   ██╔██╗ ",
    "  ╚██████╔╝██████╗ ██║   ██╔╝ ██╗",
    "   ╚═════╝ ╚═════╝ ╚═╝   ╚═╝  ╚═╝",
])


def render_qr(payload: str) -> Panel:
    qr = segno.make(payload, error="m")
    buf = io.StringIO()
    qr.terminal(out=buf, compact=True)

    return Panel(
        Align.center(Text.from_ansi(buf.getvalue())),
        title=f"[bold {BRAND}] Scan with Glyx iOS [/]",
        subtitle=f"[{DIM}]Point your camera at this code[/{DIM}]",
        box=box.ROUNDED,
        border_style=BRAND,
        padding=(1, 4),
    )


def render_info(env: dict) -> Panel:
    lines = [
        f"  [{DIM}]Device[/]   [bold white]{env['hostname']}[/] [{DIM}]({env['username']})[/]",
        f"  [{DIM}]IP[/]       [bold white]{env['ip']}:{env['port']}[/]",
    ]
    if env["agents"]:
        agents = "  ".join(f"[{ACCENT}]{a}[/]" for a in env["agents"])
        lines.append(f"  [{DIM}]Agents[/]   {agents}")
    if env.get("has_claude_token"):
        lines.append(f"  [{DIM}]Cloud[/]    [{ACCENT}]Claude Code token ready[/]")

    return Panel("\n".join(lines), box=box.SIMPLE, padding=(0, 1))


# ── Main ─────────────────────────────────────────────────────


def main() -> None:
    agents = installed_agents()
    has_token = bool(claude_code_token())

    if not has_token and "claude" in agents:
        has_token = offer_claude_auth()

    env = {
        "device_id": device_id(),
        "hostname": platform.node().split(".")[0],
        "username": os.getenv("USER", "unknown"),
        "agents": agents,
        "ip": local_ip(),
        "port": SERVER_PORT,
        "has_claude_token": has_token,
    }

    payload = qr_payload(env)

    # Brief pause so bash checkmarks are visible before clear
    time.sleep(0.4)

    # Display pairing screen
    console.clear()
    console.print()
    console.print(Align.center(Text(LOGO, style=f"bold {BRAND}")))
    console.print()
    console.print(render_qr(payload))
    console.print(render_info(env))
    console.print()
    console.print(Align.center(Text("Waiting for connection ...  Ctrl+C to exit", style=DIM)))
    console.print()

    # Free port and start MCP server
    free_port(SERVER_PORT)

    repo_dir = str(GLYX_DIR / "glyx-mcp")
    env_file = GLYX_DIR / "env"

    run_env = os.environ.copy()
    run_env["GLYX_DEVICE_ID"] = env["device_id"]

    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                run_env[key] = val

    os.chdir(repo_dir)
    os.execvpe("uv", ["uv", "run", "task", "dev"], run_env)


if __name__ == "__main__":
    main()

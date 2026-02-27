#!/usr/bin/env python3
"""Beautiful terminal pairing experience powered by Rich + segno."""

from __future__ import annotations

import io
import os
import platform
import shutil
import socket
import time
import uuid
from pathlib import Path

import segno
from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# ── Brand palette ───────────────────────────────────────────
BRAND = "bright_magenta"
ACCENT = "cyan"
DIM = "dim"

GLYX_DIR = Path.home() / ".glyx"
DEVICE_ID_FILE = GLYX_DIR / "device_id"
SERVER_PORT = 8000

console = Console(force_terminal=True)


# ── Helpers ─────────────────────────────────────────────────


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def get_or_create_device_id() -> str:
    if DEVICE_ID_FILE.exists():
        return DEVICE_ID_FILE.read_text().strip()
    device_id = str(uuid.uuid4())
    GLYX_DIR.mkdir(parents=True, exist_ok=True)
    DEVICE_ID_FILE.write_text(device_id)
    return device_id


def detect_agents() -> list[str]:
    return [a for a in ("claude", "cursor", "codex", "aider") if shutil.which(a)]


def build_qr_payload(env: dict[str, str | int | list[str]]) -> str:
    payload = (
        f"glyx://pair?"
        f"device_id={env['device_id']}"
        f"&host={env['hostname']}"
        f"&user={env['username']}"
        f"&name={env['hostname']}"
        f"&ip={env['ip']}"
        f"&server_port={env['port']}"
    )
    if env["agents"]:
        payload += f"&agents={','.join(env['agents'])}"
    return payload


# ── Rich renderables ────────────────────────────────────────


def logo_text() -> Text:
    lines = [
        "   ██████╗ ██╗  ██╗   ██╗██╗  ██╗",
        "  ██╔════╝ ██║  ╚██╗ ██╔╝╚██╗██╔╝",
        "  ██║  ███╗██║   ╚████╔╝  ╚███╔╝ ",
        "  ██║   ██║██║    ╚██╔╝   ██╔██╗ ",
        "  ╚██████╔╝██████╗ ██║   ██╔╝ ██╗",
        "   ╚═════╝ ╚═════╝ ╚═╝   ╚═╝  ╚═╝",
    ]
    return Text("\n".join(lines), style=f"bold {BRAND}")


def qr_panel(payload: str) -> Panel:
    qr = segno.make(payload, error="m")
    buf = io.StringIO()
    qr.terminal(out=buf, compact=True)
    qr_str = buf.getvalue()

    return Panel(
        Align.center(Text.from_ansi(qr_str)),
        title=f"[bold {BRAND}] Scan with Glyx iOS [/]",
        subtitle=f"[{DIM}]Point your camera at this code[/{DIM}]",
        box=box.ROUNDED,
        border_style=BRAND,
        padding=(1, 4),
    )


def info_panel(env: dict[str, str | int | list[str]]) -> Panel:
    lines: list[str] = []
    lines.append(f"  [{DIM}]Device[/]   [bold white]{env['hostname']}[/] [{DIM}]({env['username']})[/]")
    lines.append(f"  [{DIM}]IP[/]       [bold white]{env['ip']}:{env['port']}[/]")
    if env["agents"]:
        agent_str = "  ".join(f"[{ACCENT}]{a}[/]" for a in env["agents"])
        lines.append(f"  [{DIM}]Agents[/]   {agent_str}")

    return Panel(
        "\n".join(lines),
        box=box.SIMPLE,
        padding=(0, 1),
    )


# ── Main ────────────────────────────────────────────────────


def main() -> None:
    # Detect environment (fast -- no spinner needed)
    env = {
        "device_id": get_or_create_device_id(),
        "hostname": platform.node().split(".")[0],
        "username": os.getenv("USER", "unknown"),
        "agents": detect_agents(),
        "ip": get_local_ip(),
        "port": SERVER_PORT,
    }

    payload = build_qr_payload(env)

    # Brief pause so bash checkmarks are visible before we clear
    time.sleep(0.4)

    # Render the pairing screen
    console.clear()
    console.print()
    console.print(Align.center(logo_text()))
    console.print()
    console.print(qr_panel(payload))
    console.print(info_panel(env))
    console.print()
    console.print(Align.center(Text("Waiting for connection ...  Ctrl+C to exit", style=DIM)))
    console.print()

    # Hand off to the MCP server
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

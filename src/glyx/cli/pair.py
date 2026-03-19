from __future__ import annotations

import io
import json
import os
import platform
import secrets
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, TypedDict

import httpx
import segno
import typer
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
REPO_URL = "https://github.com/glyx-ai/glyx-mcp.git"
SERVER_PORT = 8000

# Supabase (same values as cloud-template/server.py)
SUPA_URL = os.environ.get("SUPABASE_URL", "https://vpopliwokdmpxhmippwc.supabase.co")
SUPA_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "sb_publishable_PFYg1B15pdweWFaL6BRDCQ_SnX-BbZf",
)

# Alphabet without ambiguous chars (0/O, 1/I/L)
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


class PairEnv(TypedDict):
    device_id: str
    hostname: str
    username: str
    agents: list[str]
    ip: str
    port: int
    has_claude_token: bool


# ── Helpers ──────────────────────────────────────────────────


def _run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip: str = s.getsockname()[0]
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


def free_port(port: int) -> None:
    """Kill any process using the given port (cross-platform via socket check + lsof fallback)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", port)) != 0:
            return  # port already free

    # Port is in use — try to free it
    if shutil.which("lsof"):
        result = _run(["lsof", "-ti", f":{port}"])
        for pid in result.stdout.strip().split("\n"):
            if pid:
                _run(["kill", "-9", pid])


def qr_payload(env: PairEnv) -> str:
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


def generate_pairing_code() -> str:
    return "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(6))


def store_pairing_code(
    code: str, payload: str, token: str | None = None, retries: int = 3
) -> str:
    """Store code→payload in Supabase pairing_codes table. Returns the stored code.

    Retries with a fresh code on 409 (unique constraint collision).
    """
    url = f"{SUPA_URL}/rest/v1/pairing_codes"
    headers = {
        "apikey": SUPA_KEY,
        "Authorization": f"Bearer {SUPA_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    row: dict[str, str] = {"code": code, "payload": payload}
    if token:
        row["claude_token"] = token

    for attempt in range(retries):
        resp = httpx.post(url, json=row, headers=headers)
        if resp.status_code == 201:
            return code
        if resp.status_code == 409 and attempt < retries - 1:
            code = generate_pairing_code()
            row["code"] = code
            continue
        resp.raise_for_status()

    return code


def cleanup_expired_codes() -> None:
    """Best-effort delete of expired pairing codes."""
    url = f"{SUPA_URL}/rest/v1/pairing_codes?expires_at=lt.now()"
    headers = {
        "apikey": SUPA_KEY,
        "Authorization": f"Bearer {SUPA_KEY}",
    }
    try:
        httpx.delete(url, headers=headers)
    except Exception:
        pass  # non-critical


def render_pairing_code(code: str) -> Panel:
    spaced = "  ".join(code[:3]) + "  -  " + "  ".join(code[3:])
    return Panel(
        Align.center(Text(spaced, style=f"bold {ACCENT}")),
        title=f"[{DIM}] Or enter this code in the app [/{DIM}]",
        box=box.ROUNDED,
        border_style=DIM,
        padding=(0, 4),
    )


def render_info(env: PairEnv) -> Panel:
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


# ── Steps ────────────────────────────────────────────────────


def step_ensure_uv() -> None:
    if shutil.which("uv"):
        console.print(f"  [bold {ACCENT}]✓[/]  uv")
        return
    with console.status(f"  [{ACCENT}]Installing uv[/]", spinner="dots"):
        subprocess.run("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True, capture_output=True)
        os.environ["PATH"] = f"{Path.home() / '.local' / 'bin'}:{os.environ['PATH']}"
    console.print(f"  [bold {ACCENT}]✓[/]  Installed uv")


def step_sync_repo() -> None:
    repo_dir = GLYX_DIR / "glyx-mcp"
    with console.status(f"  [{ACCENT}]Syncing glyx[/]", spinner="dots"):
        GLYX_DIR.mkdir(parents=True, exist_ok=True)
        if repo_dir.exists():
            shutil.rmtree(repo_dir)
        _run(["git", "clone", "--quiet", "--depth", "1", REPO_URL, str(repo_dir)])
    console.print(f"  [bold {ACCENT}]✓[/]  Synced glyx")


def step_install_deps() -> None:
    repo_dir = GLYX_DIR / "glyx-mcp"
    with console.status(f"  [{ACCENT}]Installing dependencies[/]", spinner="dots"):
        _run(["uv", "sync", "--quiet"], cwd=str(repo_dir))
    console.print(f"  [bold {ACCENT}]✓[/]  Dependencies ready")


# ── Main command ─────────────────────────────────────────────


@app.callback(invoke_without_command=True)
def pair() -> None:
    """Pair your machine with Glyx iOS."""
    # Banner
    console.clear()
    console.print()
    console.print(Align.center(Text(LOGO, style=f"bold {BRAND}")))
    console.print()
    console.print(Align.center(Text("Control AI coding agents from your phone.", style=DIM)))
    console.print(f"  [{DIM}]──────────────────────────────────────────[/]")
    console.print()

    # Detect environment (fast — no network calls)
    agents = installed_agents()
    has_token = bool(claude_code_token())

    if not has_token and "claude" in agents:
        has_token = offer_claude_auth()

    env: PairEnv = {
        "device_id": device_id(),
        "hostname": platform.node().split(".")[0],
        "username": os.getenv("USER", "unknown"),
        "agents": agents,
        "ip": local_ip(),
        "port": SERVER_PORT,
        "has_claude_token": has_token,
    }

    payload = qr_payload(env)

    # Generate and store pairing code (include Claude Code token for cloud provisioning)
    code = generate_pairing_code()
    cc_token = claude_code_token() if has_token else None
    try:
        cleanup_expired_codes()
        code = store_pairing_code(code, payload, token=cc_token)
    except Exception as exc:
        console.print(f"  [{DIM}]Pairing code unavailable: {exc}[/]")
        code = ""

    # Display pairing screen immediately (before slow repo sync)
    console.clear()
    console.print()
    console.print(Align.center(Text(LOGO, style=f"bold {BRAND}")))
    console.print()
    console.print(render_qr(payload))
    if code:
        console.print(render_pairing_code(code))
    console.print(render_info(env))
    console.print()
    console.print(Align.center(Text("Waiting for connection ...  Ctrl+C to exit", style=DIM)))
    console.print()

    # Setup steps (repo + deps for MCP executor — runs while user scans)
    step_ensure_uv()
    step_sync_repo()
    step_install_deps()

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

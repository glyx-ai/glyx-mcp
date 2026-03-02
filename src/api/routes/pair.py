"""Device pairing endpoint — serves the bootstrap script for `curl glyx.ai/pair | bash`."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["Pairing"])


@router.get("/pair", response_class=PlainTextResponse, summary="Get pairing script")
async def get_pair_script() -> str:
    """Bootstrap script that installs glyx and launches the pairing display.

    Usage: curl -sL glyx.ai/pair | bash
    """
    return PAIR_SCRIPT


PAIR_SCRIPT = r"""#!/bin/bash
# Glyx — curl glyx.ai/pair | bash
set -euo pipefail

# ── Palette ──────────────────────────────────────────────────
PB='\033[1;38;5;135m'
C='\033[38;5;81m'
G='\033[38;5;114m'
W='\033[1;37m'
D='\033[38;5;243m'
R='\033[0m'

# ── UI helpers ───────────────────────────────────────────────
FRAMES=('⣾' '⣽' '⣻' '⢿' '⡿' '⣟' '⣯' '⣷')
_pid=""
spin()  { ( set +e; trap 'exit 0' TERM; i=0; while :; do printf "\r  ${C}${FRAMES[$((i%8))]}${R}  ${W}%s${R}\033[K" "$1"; sleep 0.07; ((i++)); done ) & _pid=$!; }
stop()  { kill "$_pid" 2>/dev/null; wait "$_pid" 2>/dev/null; }
ok()    { stop; printf "\r  ${G}✓${R}  %s\033[K\n" "$1"; }
found() { printf "  ${G}✓${R}  ${D}%s${R}\n" "$1"; }

# ── Config ───────────────────────────────────────────────────
GLYX_DIR="$HOME/.glyx"
REPO_DIR="$GLYX_DIR/glyx-mcp"
REPO_URL="https://github.com/glyx-ai/glyx-mcp.git"

cleanup() { printf '\033[?25h'; jobs -p 2>/dev/null | xargs kill 2>/dev/null; true; }
trap cleanup INT TERM EXIT

# ── Banner ───────────────────────────────────────────────────
printf '\033[?25l'
clear
printf "\n"
printf "  ${PB}   ██████╗ ██╗  ██╗   ██╗██╗  ██╗${R}\n"
printf "  ${PB}  ██╔════╝ ██║  ╚██╗ ██╔╝╚██╗██╔╝${R}\n"
printf "  ${PB}  ██║  ███╗██║   ╚████╔╝  ╚███╔╝ ${R}\n"
printf "  ${PB}  ██║   ██║██║    ╚██╔╝   ██╔██╗ ${R}\n"
printf "  ${PB}  ╚██████╔╝██████╗ ██║   ██╔╝ ██╗${R}\n"
printf "  ${PB}   ╚═════╝ ╚═════╝ ╚═╝   ╚═╝  ╚═╝${R}\n"
printf "\n"
printf "  ${D}Control AI coding agents from your phone.${R}\n"
printf "  ${D}──────────────────────────────────────────${R}\n\n"

# ── Step 1: uv ──────────────────────────────────────────────
if command -v uv &>/dev/null; then
    found "uv"
else
    spin "Installing uv"
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
    export PATH="$HOME/.local/bin:$PATH"
    ok "Installed uv"
fi

# ── Step 2: Repository (always start from known-good state) ─
spin "Syncing glyx"
mkdir -p "$GLYX_DIR"
rm -rf "$REPO_DIR"
git clone --quiet --depth 1 "$REPO_URL" "$REPO_DIR" >/dev/null 2>&1
ok "Synced glyx"

# ── Step 3: Dependencies ────────────────────────────────────
spin "Installing dependencies"
cd "$REPO_DIR"
uv sync --quiet >/dev/null 2>&1
ok "Dependencies ready"

printf "\n"

# ── Hand off to Python ──────────────────────────────────────
printf '\033[?25h'
exec uv run python3 scripts/pair_display.py
"""

"""Device pairing endpoint for Glyx iOS app."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["Pairing"])


@router.get("/pair", response_class=PlainTextResponse, summary="Get pairing script")
async def get_pair_script() -> str:
    """
    Returns a shell script that sets up device pairing for the Glyx iOS app.

    Usage:
        curl -sL api.glyx.ai/pair | bash

    The script will:
    1. Generate a unique pairing code
    2. Start the glyx MCP executor
    3. Display a QR code for the iOS app to scan
    """
    return PAIR_SCRIPT


PAIR_SCRIPT = r"""#!/bin/bash
# Glyx Device Pairing Script
# Usage: curl -sL glyx.ai/pair | bash
set -e

# ── 256-color palette ────────────────────────────────────────
P='\033[38;5;135m'    # brand purple
PB='\033[1;38;5;135m' # brand purple bold
C='\033[38;5;81m'     # cyan
G='\033[38;5;114m'    # green
W='\033[1;37m'        # white bold
D='\033[38;5;243m'    # dim gray
R='\033[0m'           # reset

# ── Spinner ──────────────────────────────────────────────────
FRAMES=('⣾' '⣽' '⣻' '⢿' '⡿' '⣟' '⣯' '⣷')
_pid=""
spin() {
    ( i=0; while :; do
        printf "\r  ${C}${FRAMES[$((i%8))]}${R}  ${W}%s${R}\033[K" "$1"
        sleep 0.07; ((i++))
    done ) & _pid=$!
}
ok() {
    kill "$_pid" 2>/dev/null
    wait "$_pid" 2>/dev/null || true
    printf "\r  ${G}✓${R}  %s\033[K\n" "$1"
}
skip() { printf "  ${G}✓${R}  ${D}%s${R}\n" "$1"; }

# ── Config ───────────────────────────────────────────────────
GLYX_DIR="$HOME/.glyx"
REPO_DIR="$GLYX_DIR/glyx-mcp"
REPO_URL="https://github.com/glyx-ai/glyx-mcp.git"
mkdir -p "$GLYX_DIR"

cleanup() {
    printf '\033[?25h'
    jobs -p 2>/dev/null | xargs kill 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# ── Immediate output ─────────────────────────────────────────
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
if ! command -v uv &>/dev/null; then
    spin "Installing uv"
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
    export PATH="$HOME/.local/bin:$PATH"
    ok "Installed uv"
else
    skip "uv"
fi

# ── Step 2: Repository ──────────────────────────────────────
if [[ -d "$REPO_DIR/.git" ]]; then
    spin "Updating glyx"
    cd "$REPO_DIR" && git pull --quiet >/dev/null 2>&1
    ok "Updated glyx"
else
    spin "Downloading glyx"
    git clone --quiet "$REPO_URL" "$REPO_DIR" >/dev/null 2>&1
    ok "Downloaded glyx"
fi

# ── Step 3: Dependencies ────────────────────────────────────
spin "Installing dependencies"
cd "$REPO_DIR"
uv sync >/dev/null 2>&1
ok "Dependencies ready"

printf "\n"

# ── Hand off to Rich ────────────────────────────────────────
printf '\033[?25h'
exec uv run python3 scripts/pair_display.py
"""

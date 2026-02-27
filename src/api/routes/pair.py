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


PAIR_SCRIPT = r'''#!/bin/bash
# Glyx Device Pairing Script
# Usage: curl -sL glyx.ai/pair | bash
#
# Bash handles the noisy bootstrap (uv, git, deps) silently,
# then hands off to a Rich-powered Python script for all display.
set -e

# ── Colors (only for the bootstrap phase) ───────────────────
P='\033[1;35m'; G='\033[1;32m'; D='\033[2m'; R='\033[0m'
SPIN=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
_pid=""

spin() {
    printf '\033[?25l'
    ( i=0; while :; do
        printf "\r  ${P}${SPIN[$((i%10))]}${R}  %s" "$1"
        sleep 0.08; i=$((i+1))
    done ) & _pid=$!
}
ok() {
    kill "$_pid" 2>/dev/null
    wait "$_pid" 2>/dev/null || true
    printf "\r  ${G}✓${R}  %s\n" "$1"
    printf '\033[?25h'
}
ok_skip() { printf "  ${G}✓${R}  %s\n" "$1"; }

# ── Config ──────────────────────────────────────────────────
GLYX_DIR="$HOME/.glyx"
REPO_DIR="$GLYX_DIR/glyx-mcp"
REPO_URL="https://github.com/glyx-ai/glyx-mcp.git"
mkdir -p "$GLYX_DIR"

cleanup() { printf '\033[?25h'; jobs -p 2>/dev/null | xargs kill 2>/dev/null||true; exit 0; }
trap cleanup INT TERM

# ── Bootstrap header ────────────────────────────────────────
clear
printf "\n"
printf "  ${P}   ██████╗ ██╗  ██╗   ██╗██╗  ██╗${R}\n"
printf "  ${P}  ██╔════╝ ██║  ╚██╗ ██╔╝╚██╗██╔╝${R}\n"
printf "  ${P}  ██║  ███╗██║   ╚████╔╝  ╚███╔╝ ${R}\n"
printf "  ${P}  ██║   ██║██║    ╚██╔╝   ██╔██╗ ${R}\n"
printf "  ${P}  ╚██████╔╝██████╗ ██║   ██╔╝ ██╗${R}\n"
printf "  ${P}   ╚═════╝ ╚═════╝ ╚═╝   ╚═╝  ╚═╝${R}\n"
printf "\n  ${D}Setting up your machine...${R}\n\n"

# ── Step 1: uv ──────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    spin "Installing uv"
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
    export PATH="$HOME/.local/bin:$PATH"
    ok "Installed uv"
else
    ok_skip "uv"
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

# ── Hand off to Rich ────────────────────────────────────────
exec uv run python3 scripts/pair_display.py
'''

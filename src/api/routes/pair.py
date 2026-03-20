"""Pairing & cloud setup endpoints — bootstrap scripts served via curl | bash."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["Pairing"])


@router.get("/pair", response_class=PlainTextResponse, summary="Get pairing script")
async def get_pair_script() -> str:
    """Bootstrap script for device pairing.

    Usage: curl -sL glyx.ai/pair | bash
    """
    return PAIR_SCRIPT


@router.get("/cloud", response_class=PlainTextResponse, summary="Get cloud setup script")
async def get_cloud_script() -> str:
    """Bootstrap script for cloud agent setup (Claude Code token transfer).

    Usage: curl -sL glyx.ai/cloud | bash
    """
    return CLOUD_SCRIPT


PAIR_SCRIPT = r"""#!/bin/bash
set -euo pipefail

# Immediate branded output
printf '\n'
printf '  \033[1;35m   ██████╗ ██╗  ██╗   ██╗██╗  ██╗\033[0m\n'
printf '  \033[1;35m  ██╔════╝ ██║  ╚██╗ ██╔╝╚██╗██╔╝\033[0m\n'
printf '  \033[1;35m  ██║  ███╗██║   ╚████╔╝  ╚███╔╝ \033[0m\n'
printf '  \033[1;35m  ██║   ██║██║    ╚██╔╝   ██╔██╗ \033[0m\n'
printf '  \033[1;35m  ╚██████╔╝██████╗ ██║   ██╔╝ ██╗\033[0m\n'
printf '  \033[1;35m   ╚═════╝ ╚═════╝ ╚═╝   ╚═╝  ╚═╝\033[0m\n'
printf '\n'
printf '  \033[1;36mDevice Pairing\033[0m\n'
printf '  \033[2m──────────────────────────────────────────\033[0m\n'
printf '\n'

_spin() {
  local msg="$1"
  local frames='⣾⣽⣻⢿⡿⣟⣯⣷'
  local i=0
  tput civis 2>/dev/null
  while true; do
    printf "\r  \033[35m${frames:i%${#frames}:1}\033[0m  %s" "$msg"
    i=$((i + 1))
    sleep 0.08
  done
}

_stop_spin() {
  if [ -n "${SPIN_PID:-}" ]; then
    kill "$SPIN_PID" 2>/dev/null
    wait "$SPIN_PID" 2>/dev/null
    printf "\r\033[2K"
    tput cnorm 2>/dev/null
  fi
}
trap _stop_spin EXIT

if ! command -v uv &>/dev/null; then
  _spin "Installing uv" &
  SPIN_PID=$!
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
  _stop_spin
  export PATH="$HOME/.local/bin:$PATH"
  printf '  \033[1;36m✓\033[0m  uv installed\n'
else
  printf '  \033[1;36m✓\033[0m  uv\n'
fi

_spin "Preparing pairing" &
SPIN_PID=$!
uv tool install --force --quiet "glyx @ git+https://github.com/glyx-ai/glyx-mcp.git" >/dev/null 2>&1
_stop_spin
printf '  \033[1;36m✓\033[0m  Ready\n\n'

exec glyx-pair
"""

CLOUD_SCRIPT = r"""#!/bin/bash
set -euo pipefail

# Immediate branded output
printf '\n'
printf '  \033[1;35m   ██████╗ ██╗  ██╗   ██╗██╗  ██╗\033[0m\n'
printf '  \033[1;35m  ██╔════╝ ██║  ╚██╗ ██╔╝╚██╗██╔╝\033[0m\n'
printf '  \033[1;35m  ██║  ███╗██║   ╚████╔╝  ╚███╔╝ \033[0m\n'
printf '  \033[1;35m  ██║   ██║██║    ╚██╔╝   ██╔██╗ \033[0m\n'
printf '  \033[1;35m  ╚██████╔╝██████╗ ██║   ██╔╝ ██╗\033[0m\n'
printf '  \033[1;35m   ╚═════╝ ╚═════╝ ╚═╝   ╚═╝  ╚═╝\033[0m\n'
printf '\n'
printf '  \033[1;36mCloud Agent Setup\033[0m\n'
printf '  \033[2m──────────────────────────────────────────\033[0m\n'
printf '\n'

# Spinner runs until killed
_spin() {
  local msg="$1"
  local frames='⣾⣽⣻⢿⡿⣟⣯⣷'
  local i=0
  tput civis 2>/dev/null
  while true; do
    printf "\r  \033[35m${frames:i%${#frames}:1}\033[0m  %s" "$msg"
    i=$((i + 1))
    sleep 0.08
  done
}

_stop_spin() {
  if [ -n "${SPIN_PID:-}" ]; then
    kill "$SPIN_PID" 2>/dev/null
    wait "$SPIN_PID" 2>/dev/null
    printf "\r\033[2K"
    tput cnorm 2>/dev/null
  fi
}
trap _stop_spin EXIT

# Install uv if needed
if ! command -v uv &>/dev/null; then
  _spin "Installing uv" &
  SPIN_PID=$!
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
  _stop_spin
  export PATH="$HOME/.local/bin:$PATH"
  printf '  \033[1;36m✓\033[0m  uv installed\n'
else
  printf '  \033[1;36m✓\033[0m  uv\n'
fi

# Pre-fetch the package (the slow part) with a spinner
_spin "Preparing cloud setup" &
SPIN_PID=$!
uv tool install --force --quiet "glyx @ git+https://github.com/glyx-ai/glyx-mcp.git" >/dev/null 2>&1
_stop_spin
printf '  \033[1;36m✓\033[0m  Ready\n\n'

# Hand off to the CLI (instant now — already installed)
exec glyx-cloud
"""

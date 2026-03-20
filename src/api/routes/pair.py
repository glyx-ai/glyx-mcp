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
printf '\n  \033[1;35m⚡ Glyx\033[0m — setting up...\n\n'
if ! command -v uv &>/dev/null; then
  printf '  Installing uv...\n'
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
  export PATH="$HOME/.local/bin:$PATH"
fi
printf '  Launching pairing...\n'
exec uvx --from "git+https://github.com/glyx-ai/glyx-mcp.git" glyx-pair
"""

CLOUD_SCRIPT = r"""#!/bin/bash
set -euo pipefail
printf '\n  \033[1;35m⚡ Glyx\033[0m — Cloud Agent Setup\n\n'
if ! command -v uv &>/dev/null; then
  printf '  Installing uv...\n'
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
  export PATH="$HOME/.local/bin:$PATH"
fi
exec uvx --from "git+https://github.com/glyx-ai/glyx-mcp.git" glyx-cloud
"""

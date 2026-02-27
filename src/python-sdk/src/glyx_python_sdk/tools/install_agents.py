"""Install AI coding agent CLIs."""

from __future__ import annotations

import asyncio
import logging

from fastmcp import Context

logger = logging.getLogger(__name__)

AGENT_PACKAGES = {
    "opencode": "opencode-ai@latest",
    "claude": "@anthropic-ai/claude-code",
    "codex": "@openai/codex",
}


async def install_agents(
    ctx: Context,
    agents: str = "opencode,claude,codex",
) -> str:
    """Install AI coding agent CLIs via npm.

    Args:
        agents: Comma-separated list of agents to install (opencode, claude, codex)
        ctx: FastMCP context (injected)

    Returns:
        Installation results
    """
    requested = [a.strip() for a in agents.split(",")]
    results: list[str] = []

    for agent in requested:
        package = AGENT_PACKAGES.get(agent)
        if not package:
            results.append(f"❌ Unknown agent: {agent}")
            continue

        await ctx.info(f"Installing {agent}...", extra={"package": package})

        proc = await asyncio.create_subprocess_exec(
            "npm",
            "install",
            "-g",
            package,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            results.append(f"✅ {agent} installed successfully")
        else:
            error = stderr.decode().strip() or stdout.decode().strip()
            results.append(f"❌ {agent} failed: {error}")

    return "\n".join(results)

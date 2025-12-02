"""Cursor agent with OpenAI Agent SDK session management."""

from __future__ import annotations

import logging
import os
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from agents import Agent, Runner, SQLiteSession, function_tool
from fastmcp import Context

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Session database location - use /tmp for cloud environments
SESSION_DB = Path(os.environ.get("GLYX_SESSION_DB", "/tmp/glyx_sessions.db"))


@function_tool
async def cursor_agent(prompt: str, model: str = "auto", files: str | None = None) -> str:
    """Execute cursor-agent CLI with the given prompt and model."""
    cmd = ["cursor-agent", "-p", "--output-format", "json"]

    if model:
        cmd.extend(["--model", model])

    if files:
        cmd.extend(["--files", files])

    cmd.append(prompt)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        return f"Error: {result.stderr}"

    return result.stdout


async def use_cursor_with_session(
    prompt: str,
    ctx: Context,
    model: str = "gpt-5",
    files: str | None = None,
    session_id: str | None = None,
) -> str:
    """Execute cursor agent with OpenAI Agent SDK session management."""
    if not session_id:
        session_id = str(uuid.uuid4())

    await ctx.info(f"🚀 Starting cursor agent with session {session_id}")

    # Create session
    session = SQLiteSession(session_id, str(SESSION_DB))

    # Create OpenAI agent that uses cursor as a tool
    agent = Agent(
        name="CursorOrchestrator",
        instructions=f"""You are an AI coding assistant that uses the cursor-agent CLI tool.

Model: {model}
Files: {files or 'none specified'}
""",
        tools=[cursor_agent],
    )

    try:
        result = await Runner.run(agent, prompt, session=session)
        await ctx.info(f"✅ Session {session_id} completed")
        return result.final_output or str(result.messages[-1].content) if result.messages else "No output"
    except Exception as e:
        logger.error(f"Session execution failed: {e}")
        await ctx.info(f"❌ Session {session_id} failed")
        raise

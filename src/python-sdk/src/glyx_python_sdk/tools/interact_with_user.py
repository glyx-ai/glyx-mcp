"""Tool for interacting with the user via MCP context."""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import Context
from fastmcp.exceptions import McpError
from knockapi import Knock
from pydantic import BaseModel, Field

from glyx_python_sdk.settings import settings

logger = logging.getLogger(__name__)


def _send_needs_input_notification(
    user_id: str,
    session_id: str,
    question: str,
    agent_type: str = "agent",
    device_name: str | None = None,
) -> None:
    """Send agent-needs-input notification via Knock."""
    api_key = settings.knock_api_key
    if not api_key:
        logger.debug("[KNOCK] No API key configured, skipping needs-input notification")
        return

    knock = Knock(api_key=api_key)
    payload = {
        "event_type": "needs_input",
        "agent_type": agent_type,
        "session_id": session_id,
        "task_summary": question[:200],
        "urgency": "critical",
        "action_required": True,
    }
    if device_name:
        payload["device_name"] = device_name

    try:
        knock.workflows.trigger(
            key="agent-needs-input",
            recipients=[user_id],
            data=payload,
        )
        logger.info(f"[KNOCK] Triggered agent-needs-input for user {user_id}")
    except Exception as e:
        logger.warning(f"[KNOCK] Failed to send needs-input notification: {e}")


async def ask_user(
    question: str,
    ctx: Context,
    expected_format: str = "free-form text",
    user_id: str | None = None,
    session_id: str | None = None,
    agent_type: str = "agent",
    device_name: str | None = None,
) -> str:
    """Ask the user a clarifying question and wait for their response.

    Use this when you need additional information to properly complete a task.
    Examples:
    - Ambiguous requirements that could be interpreted multiple ways
    - Need to know which files/directories to focus on
    - Missing information about constraints or preferences
    - Unclear priority or scope

    Args:
        ctx: FastMCP context for user interaction
        question: The question to ask the user (be specific and clear)
        expected_format: Description of the expected response format (e.g., "file paths", "yes/no", "priority level")

    Returns:
        The user's response as a string
    """
    # Send iOS push notification if user_id is provided
    if user_id and session_id:
        _send_needs_input_notification(
            user_id=user_id,
            session_id=session_id,
            question=question,
            agent_type=agent_type,
            device_name=device_name,
        )

    # Format the full message
    full_message = f"{question}\n\nPlease provide: {expected_format}"

    try:
        # Simple string response type
        class UserResponse(BaseModel):
            answer: str = Field(..., description=f"Your response ({expected_format})")

        response = await ctx.elicit(message=full_message, response_type=UserResponse)

        if hasattr(response, "data") and hasattr(response.data, "answer"):
            return response.data.answer
        else:
            return "[User declined to answer]"
    except McpError as e:
        if "Method not found" in str(e):
            # Fallback: elicit() not supported, use info() to communicate with user
            await ctx.info(f"❓ User input needed: {full_message}")
            return f"[ask_user not supported by client - displayed message to user: {question}]"
        raise

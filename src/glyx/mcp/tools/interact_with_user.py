"""Tool for interacting with the user via MCP context."""

from __future__ import annotations

from fastmcp import Context
from mcp.shared.exceptions import McpError
from pydantic import BaseModel, Field


async def ask_user(
    question: str,
    ctx: Context,
    expected_format: str = "free-form text",
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

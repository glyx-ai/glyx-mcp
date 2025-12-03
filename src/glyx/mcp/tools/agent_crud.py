"""CRUD tools for managing agent configurations in Supabase."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from pydantic import Field

from glyx.core.supabase_loader import (
    delete_agent_from_supabase,
    list_agents_from_supabase,
    save_agent_to_supabase,
)

logger = logging.getLogger(__name__)


def create_agent(
    agent_key: Annotated[str, Field(description="Unique key for the agent (e.g., 'my_custom_agent')")],
    command: Annotated[str, Field(description="CLI command to execute (e.g., 'aider', 'cursor-agent')")],
    args: Annotated[dict[str, dict[str, Any]], Field(description="Argument specifications as a dict of ArgSpec objects")],
    description: Annotated[str | None, Field(description="Human-readable description of the agent")] = None,
    version: Annotated[str | None, Field(description="Version string for the agent")] = None,
    capabilities: Annotated[list[str] | None, Field(description="List of capability tags")] = None,
    user_id: Annotated[str | None, Field(description="User ID (None for global agents)")] = None,
) -> str:
    """Create a new agent configuration in Supabase.

    Example args structure:
    {
        "prompt": {"flag": "", "type": "string", "required": true, "description": "Task prompt"},
        "model": {"flag": "--model", "type": "string", "default": "gpt-4", "description": "Model to use"},
        "verbose": {"flag": "--verbose", "type": "bool", "default": false, "description": "Enable verbose output"}
    }
    """
    logger.info(f"create_agent called: agent_key={agent_key}, command={command}")

    result = save_agent_to_supabase(
        agent_key=agent_key,
        command=command,
        args=args,
        user_id=user_id,
        description=description,
        version=version,
        capabilities=capabilities,
    )

    if result:
        return json.dumps({"status": "created", "agent": result})
    return json.dumps({"status": "error", "message": "Failed to create agent"})


def list_agents(
    user_id: Annotated[str | None, Field(description="User ID to list agents for (None for global only)")] = None,
) -> str:
    """List all available agents (user-specific + global).

    Returns all agents visible to the specified user, including their configurations.
    """
    logger.info(f"list_agents called: user_id={user_id}")

    agents = list_agents_from_supabase(user_id)

    formatted = [
        {
            "agent_key": a["agent_key"],
            "command": a["command"],
            "description": a.get("description"),
            "is_global": a.get("user_id") is None,
            "capabilities": a.get("capabilities", []),
        }
        for a in agents
    ]

    return json.dumps({"agents": formatted, "count": len(formatted)})


def delete_agent(
    agent_key: Annotated[str, Field(description="Key of the agent to delete")],
    user_id: Annotated[str, Field(description="User ID (required - can only delete your own agents)")],
) -> str:
    """Delete a user-owned agent from Supabase.

    Note: Users can only delete their own agents, not global agents.
    """
    logger.info(f"delete_agent called: agent_key={agent_key}, user_id={user_id}")

    success = delete_agent_from_supabase(agent_key, user_id)

    if success:
        return json.dumps({"status": "deleted", "agent_key": agent_key})
    return json.dumps({"status": "error", "message": f"Agent '{agent_key}' not found or not owned by user"})


def get_agent(
    agent_key: Annotated[str, Field(description="Key of the agent to retrieve")],
    user_id: Annotated[str | None, Field(description="User ID (None for global agents only)")] = None,
) -> str:
    """Get detailed configuration for a specific agent.

    Returns the full agent configuration including args schema.
    """
    logger.info(f"get_agent called: agent_key={agent_key}, user_id={user_id}")

    agents = list_agents_from_supabase(user_id)
    agent = next((a for a in agents if a["agent_key"] == agent_key), None)

    if agent:
        return json.dumps({"status": "found", "agent": agent})
    return json.dumps({"status": "not_found", "message": f"Agent '{agent_key}' not found"})

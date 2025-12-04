"""Supabase agent loader for dynamic agent discovery."""

import logging
import os
from typing import Any

from supabase import create_client, Client

from glyx_python_sdk.agent import AgentConfig, ArgSpec

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


def get_supabase_client() -> Client:
    """Create Supabase client from environment variables."""
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def row_to_agent_config(row: dict[str, Any]) -> AgentConfig:
    """Convert a Supabase row to AgentConfig."""
    args = {k: ArgSpec(**v) for k, v in row["args"].items()}
    return AgentConfig(
        agent_key=row["agent_key"],
        command=row["command"],
        args=args,
        description=row.get("description"),
        version=row.get("version"),
        capabilities=row.get("capabilities", []),
    )


def load_agents_from_supabase(user_id: str | None = None) -> list[AgentConfig]:
    """Load agents from Supabase for a user (+ global agents).

    Args:
        user_id: Optional user ID to load user-specific agents.
                 If None, only global agents are loaded.

    Returns:
        List of AgentConfig instances from the database.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        logger.warning("Supabase credentials not configured, skipping DB agent loading")
        return []

    try:
        client = get_supabase_client()
        query = client.table("agents").select("*").eq("is_active", True)

        if user_id:
            query = query.or_(f"user_id.eq.{user_id},user_id.is.null")
        else:
            query = query.is_("user_id", "null")

        response = query.execute()
        configs = [row_to_agent_config(row) for row in response.data]
        logger.info(f"Loaded {len(configs)} agents from Supabase")
        return configs

    except Exception as e:
        logger.error(f"Failed to load agents from Supabase: {e}")
        return []


def save_agent_to_supabase(
    agent_key: str,
    command: str,
    args: dict[str, dict[str, Any]],
    user_id: str | None = None,
    description: str | None = None,
    version: str | None = None,
    capabilities: list[str] | None = None,
) -> dict[str, Any] | None:
    """Save a new agent configuration to Supabase.

    Args:
        agent_key: Unique key for the agent
        command: CLI command to execute
        args: Dict of argument specifications
        user_id: Optional user ID (None for global agents)
        description: Optional agent description
        version: Optional version string
        capabilities: Optional list of capability tags

    Returns:
        Created row data or None on failure.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        logger.error("Supabase credentials not configured")
        return None

    try:
        client = get_supabase_client()
        data = {
            "agent_key": agent_key,
            "command": command,
            "args": args,
            "user_id": user_id,
            "description": description,
            "version": version,
            "capabilities": capabilities or [],
            "is_active": True,
        }

        response = client.table("agents").insert(data).execute()
        logger.info(f"Created agent '{agent_key}' in Supabase")
        return response.data[0] if response.data else None

    except Exception as e:
        logger.error(f"Failed to save agent to Supabase: {e}")
        return None


def delete_agent_from_supabase(agent_key: str, user_id: str) -> bool:
    """Delete a user-owned agent from Supabase.

    Args:
        agent_key: Key of the agent to delete
        user_id: User ID (ensures user can only delete their own agents)

    Returns:
        True if deleted, False otherwise.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        logger.error("Supabase credentials not configured")
        return False

    try:
        client = get_supabase_client()
        response = client.table("agents").delete().eq("agent_key", agent_key).eq("user_id", user_id).execute()

        deleted = len(response.data) > 0
        if deleted:
            logger.info(f"Deleted agent '{agent_key}' for user {user_id}")
        else:
            logger.warning(f"Agent '{agent_key}' not found for user {user_id}")
        return deleted

    except Exception as e:
        logger.error(f"Failed to delete agent from Supabase: {e}")
        return False


def list_agents_from_supabase(user_id: str | None = None) -> list[dict[str, Any]]:
    """List all agents visible to a user.

    Args:
        user_id: Optional user ID. If provided, returns user's agents + global.
                 If None, returns only global agents.

    Returns:
        List of agent rows from the database.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        logger.warning("Supabase credentials not configured")
        return []

    try:
        client = get_supabase_client()
        query = client.table("agents").select("*").eq("is_active", True)

        if user_id:
            query = query.or_(f"user_id.eq.{user_id},user_id.is.null")
        else:
            query = query.is_("user_id", "null")

        response = query.execute()
        return response.data

    except Exception as e:
        logger.error(f"Failed to list agents from Supabase: {e}")
        return []

"""Memory tools for storing and retrieving project context using Mem0."""

from __future__ import annotations

from mem0 import MemoryClient

from glyx_mcp.settings import settings

mem0_client = MemoryClient(api_key=settings.mem0_api_key) if settings.mem0_api_key else None


def search_memory(query: str, user_id: str = "default_user", limit: int = 5) -> str:
    """Search past conversations and project context from memory.

    Use this to recall architecture decisions, code patterns, file locations, and past solutions.

    Args:
        query: Search query (e.g., "authentication implementation", "API patterns", "test setup")
        user_id: User identifier for memory segmentation
        limit: Maximum number of memories to return

    Returns:
        Relevant memories from past conversations and project work
    """
    if not mem0_client:
        return "Memory feature not available - MEM0_API_KEY not configured"

    memories = mem0_client.search(query=query, user_id=user_id, limit=limit)
    return str(memories)


def save_memory(text: str, user_id: str = "default_user") -> str:
    """Save important project information to memory for future reference.

    Use this to persist architecture decisions, code patterns, file locations, preferences, and solutions.

    Args:
        text: Information to store (e.g., "Project uses Pydantic for all validation", "Auth in src/auth/")
        user_id: User identifier for memory segmentation

    Returns:
        Confirmation of memory storage
    """
    if not mem0_client:
        return "Memory feature not available - MEM0_API_KEY not configured"

    result = mem0_client.add(messages=text, user_id=user_id)
    return f"Memory saved: {result}"

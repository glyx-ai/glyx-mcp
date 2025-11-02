"""Memory tools for storing and retrieving project context using Mem0."""

from __future__ import annotations

from enum import Enum
from typing import Any

from mem0 import MemoryClient
from pydantic import BaseModel, Field

from glyx_mcp.settings import settings

mem0_client = MemoryClient(api_key=settings.mem0_api_key) if settings.mem0_api_key else None


class MemoryEvent(str, Enum):
    """Event types for memory operations."""

    ADD = "ADD"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class Message(BaseModel):
    """Message structure for conversation memory."""

    role: str = Field(..., description="Either 'user' or 'assistant'")
    content: str = Field(..., description="The actual message text")


class GlyxMemory(BaseModel):
    """Structured memory request matching Mem0 API v2."""

    messages: list[Message] | str = Field(
        ...,
        description="Array of message objects or a single string for simple memories",
    )
    agent_id: str | None = Field(None, description="Unique identifier of the agent")
    user_id: str | None = Field(None, description="Unique identifier of the user")
    app_id: str | None = Field(None, description="Unique identifier of the application")
    run_id: str | None = Field(None, description="Unique identifier of the run")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata (location, time, ids, etc.)")
    includes: str | None = Field(None, min_length=1, description="Specific preferences to include")
    excludes: str | None = Field(None, min_length=1, description="Specific preferences to exclude")
    infer: bool = Field(True, description="Whether to infer memories or directly store messages")
    output_format: str | None = Field("v1.1", description="Response format (v1.1 recommended)")
    custom_categories: list[dict[str, str]] | None = Field(None, description="Custom category definitions")
    custom_instructions: str | None = Field(None, description="Project-specific guidelines for handling memories")
    immutable: bool = Field(False, description="Whether the memory is immutable")
    async_mode: bool = Field(True, description="Whether to add memory asynchronously")
    timestamp: int | None = Field(None, description="Unix timestamp of the memory")
    expiration_date: str | None = Field(None, description="Expiration date in YYYY-MM-DD format")
    org_id: str | None = Field(None, description="Organization identifier")
    project_id: str | None = Field(None, description="Project identifier")
    version: str | None = Field(None, description="API version (v2 recommended)")
    enable_graph: bool = Field(True, description="Enable graph-based memory relationships")


# Custom categories for coding project memory
CUSTOM_CATEGORIES = [
    {"category": "architecture", "description": "System design, component structure, module organization, design patterns, and how the system is architected"},
    {"category": "integrations", "description": "How different systems connect: MCP tools, SDK integrations, API boundaries, third-party services, and inter-component communication"},
    {"category": "code_style_guidelines", "description": "Project conventions, coding style preferences, naming patterns, formatting rules, and code quality standards"},
    {"category": "project_id", "description": "Project identity, purpose, core mission, what the project does, and high-level overview"},
    {"category": "observability", "description": "Logging strategies, tracing implementation, monitoring setup, debugging approaches, and error handling patterns"},
    {"category": "product", "description": "Product features, user-facing functionality, capabilities, and what the system delivers to users"},
    {"category": "key_concept", "description": "Important concepts, patterns, paradigms, and fundamental ideas that are central to understanding the system"},
]


def setup_custom_categories() -> str:
    """Initialize custom categories for the project. Call once during setup."""
    if not mem0_client:
        return "Memory feature not available - MEM0_API_KEY not configured"

    result = mem0_client.project.update(custom_categories=CUSTOM_CATEGORIES)
    return f"Custom categories configured: {result}"


def search_memory(query: str, user_id: str = "default_user", limit: int = 5) -> str:
    """Search past conversations and project context from memory.

    Use this to recall architecture decisions, code patterns, file locations, and past solutions.

    Args:
        query: Search query (e.g., "authentication implementation", "API patterns", "test setup")
        user_id: User identifier for memory segmentation
        limit: Maximum number of memories to return

    Returns:
        Relevant memories from past conversations and project work, including graph relationships
    """
    if not mem0_client:
        return "Memory feature not available - MEM0_API_KEY not configured"

    memories = mem0_client.search(query=query, user_id=user_id, limit=limit, enable_graph=True)
    return str(memories)


def save_memory(
    messages: str | list[dict[str, str]],
    agent_id: str | None = None,
    user_id: str = "default_user",
    metadata: dict[str, Any] | None = None,
    run_id: str | None = None,
    timestamp: int | None = None,
) -> str:
    """Save structured memory with metadata and context.

    The agent is responsible for determining what metadata to include based on the context.

    Args:
        messages: Content to store (string or list of message dicts with 'role' and 'content')
        agent_id: Identifier of the agent creating this memory (e.g., "orchestrator", "aider", "grok")
        user_id: User identifier for memory segmentation
        metadata: Additional context (e.g., {"directory_name": "glyx-mcp", "category": "architecture", "user_intention": "refactor"})
        run_id: Unique identifier for the current execution run
        timestamp: Unix timestamp of when this memory was created

    Returns:
        Confirmation of memory storage

    Example:
        save_memory(
            messages="Orchestrator uses OpenAI Agents SDK for parallel execution",
            agent_id="orchestrator",
            metadata={"directory_name": "glyx-mcp", "category": "architecture"},
        )
    """
    if not mem0_client:
        return "Memory feature not available - MEM0_API_KEY not configured"

    # Build the memory request
    memory = GlyxMemory(
        messages=messages,
        agent_id=agent_id,
        user_id=user_id,
        metadata=metadata,
        run_id=run_id,
        timestamp=timestamp,
        enable_graph=True,
    )

    # Convert to dict and extract fields for mem0_client.add()
    memory_dict = memory.model_dump(exclude_none=True)
    enable_graph = memory_dict.pop("enable_graph", True)

    result = mem0_client.add(enable_graph=enable_graph, **memory_dict)
    return f"Memory saved: {result}"


def delete_all_memories(user_id: str = "default_user") -> str:
    """Delete ALL memories for a user. Use with caution!

    Args:
        user_id: User identifier for memory segmentation

    Returns:
        Confirmation of deletion
    """
    if not mem0_client:
        return "Memory feature not available - MEM0_API_KEY not configured"

    result = mem0_client.delete_all(user_id=user_id)
    return f"All memories deleted for user {user_id}: {result}"

"""Memory tools for storing and retrieving project context using Mem0."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated, Literal, Optional

from mem0 import MemoryClient
from pydantic import Field

from glyx_sdk.settings import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_mem0_client() -> MemoryClient:
    """Lazy initialize Mem0 client on first use."""
    logger.info("Initializing Mem0 client...")
    return MemoryClient(api_key=settings.mem0_api_key)


# Custom categories for coding project memory
CUSTOM_CATEGORIES = [
    {
        "category": "architecture",
        "description": "System design, component structure, module organization, design patterns, and how the system is architected",
    },
    {
        "category": "integrations",
        "description": "How different systems connect: MCP tools, SDK integrations, API boundaries, third-party services, and inter-component communication",
    },
    {
        "category": "code_style_guidelines",
        "description": "Project conventions, coding style preferences, naming patterns, formatting rules, and code quality standards",
    },
    {
        "category": "project_id",
        "description": "Project identity, purpose, core mission, what the project does, and high-level overview",
    },
    {
        "category": "observability",
        "description": "Logging strategies, tracing implementation, monitoring setup, debugging approaches, and error handling patterns",
    },
    {
        "category": "product",
        "description": "Product features, user-facing functionality, capabilities, and what the system delivers to users",
    },
    {
        "category": "key_concept",
        "description": "Important concepts, patterns, paradigms, and fundamental ideas that are central to understanding the system",
    },
    {
        "category": "tasks",
        "description": "Task tracking, orchestration progress, agent assignments, task status updates, and work coordination",
    },
]


def search_memory(
    query: Annotated[str, Field(description="Search query (e.g., 'authentication implementation', 'API patterns')")],
    limit: Annotated[int, Field(description="Maximum number of memories to return", ge=1, le=100)] = 5,
    user_id: Annotated[str, Field(description="User identifier for memory segmentation")] = "glyx_app_1",
    agent_id: Annotated[Optional[str], Field(description="Filter by agent (e.g., 'orchestrator', 'aider')")] = None,
    category: Annotated[
        Optional[
            Literal[
                "architecture",
                "integrations",
                "code_style_guidelines",
                "project_id",
                "observability",
                "product",
                "key_concept",
                "tasks",
            ]
        ],
        Field(description="Filter by category"),
    ] = None,
) -> str:
    """Search past conversations and project context from memory.

    Use this to recall architecture decisions, code patterns, file locations, and past solutions.
    """
    logger.info(f"search_memory called with query={query}, limit={limit}, user_id={user_id}")

    filter_dict = {
        k: v
        for k, v in {
            "user_id": user_id,
            "agent_id": agent_id,
            "category": category,
        }.items()
        if v is not None
    }
    logger.debug(f"Calling mem0_client.search with filters={filter_dict}")

    memories = _get_mem0_client().search(query=query, filters=filter_dict)

    import json

    result = json.dumps(memories)
    logger.info(f"search_memory returning {len(result)} characters")
    return result


def save_memory(
    content: Annotated[str, Field(description="The memory content to store")],
    agent_id: Annotated[str, Field(description="Agent identifier (e.g., 'orchestrator', 'aider', 'grok', 'claude')")],
    run_id: Annotated[str, Field(description="Unique identifier for the current execution run")],
    user_id: Annotated[str, Field(description="User identifier for memory segmentation")] = "glyx_app_1",
    directory_name: Annotated[Optional[str], Field(description="Directory or project name (e.g., 'glyx-mcp')")] = None,
    category: Annotated[
        Optional[
            Literal[
                "architecture",
                "integrations",
                "code_style_guidelines",
                "project_id",
                "observability",
                "product",
                "key_concept",
                "tasks",
            ]
        ],
        Field(description="Memory category"),
    ] = None,
) -> str:
    """Save structured memory with metadata and context.

    Categories:
    - architecture: System design, component structure, design patterns
    - integrations: MCP tools, SDK integrations, APIs, third-party services
    - code_style_guidelines: Project conventions, coding style, naming patterns
    - project_id: Project identity, purpose, core mission
    - observability: Logging, tracing, monitoring, debugging approaches
    - product: Product features, user-facing functionality
    - key_concept: Important concepts, patterns, paradigms
    - tasks: Task tracking, orchestration progress, agent assignments
    """
    logger.info(f"save_memory called: content={content[:100]}..., agent_id={agent_id}, category={category}")

    import time

    timestamp = int(time.time())
    logger.debug(f"Generated timestamp: {timestamp}")

    metadata_dict = {}
    if directory_name:
        metadata_dict["directory_name"] = directory_name
    if category:
        metadata_dict["category"] = category

    logger.debug(f"Building memory with metadata={metadata_dict}")

    memory_dict = {
        "messages": content,
        "agent_id": agent_id,
        "user_id": user_id,
        "run_id": run_id,
        "timestamp": timestamp,
    }
    if metadata_dict:
        memory_dict["metadata"] = metadata_dict

    logger.debug(f"Calling mem0_client.add with enable_graph=True")
    result = _get_mem0_client().add(enable_graph=True, **memory_dict)

    response = f"Memory saved: {result}"
    logger.info(f"save_memory returning: {response}")
    return response


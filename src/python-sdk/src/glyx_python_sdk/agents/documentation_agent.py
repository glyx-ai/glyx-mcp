"""OpenAI Agent SDK agent for retrieving documentation via Context7 MCP."""

import logging

from agents import Agent, Runner

from glyx_python_sdk.mcp_registry import CONTEXT7

logger = logging.getLogger(__name__)


def create_documentation_agent(model: str = "gpt-4o") -> Agent:
    """Create a DocumentationAgent using Context7 MCP for documentation retrieval.

    Args:
        model: Model for the agent's reasoning

    Returns:
        Agent instance with Context7 MCP tools

    Example:
        ```python
        from agents import Runner
        from glyx_python_sdk.agents.documentation_agent import create_documentation_agent

        async with create_documentation_agent() as agent:
            result = await Runner.run(agent, "Get docs for fastmcp CLI")
        ```
    """
    return Agent(
        name="DocumentationAgent",
        instructions=(
            "You retrieve documentation using Context7. "
            "Use the available tools to search and fetch library documentation."
        ),
        model=model,
        mcp_servers=[CONTEXT7],
    )


async def retrieve_documentation_streamed(query: str, model: str = "gpt-4o"):
    """Retrieve documentation with streaming events.

    Args:
        query: Documentation query (library name, topic, etc.)
        model: Model to use

    Yields:
        Stream events during retrieval
    """
    async with CONTEXT7:
        agent = create_documentation_agent(model=model)
        result = Runner.run_streamed(
            starting_agent=agent,
            input=query,
        )
        async for event in result.stream_events():
            yield event

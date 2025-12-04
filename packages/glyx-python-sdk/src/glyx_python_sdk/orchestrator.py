"""Core orchestrator logic."""
from __future__ import annotations

import logging

from agents import Agent, Runner, SQLiteSession, function_tool
from agents.extensions.models.litellm_model import LitellmModel
from agents.items import MessageOutputItem, ReasoningItem, ToolCallItem, ToolCallOutputItem
from glyx_python_sdk.agent import AgentKey, AgentResult, ComposableAgent
from glyx_python_sdk.settings import settings
from glyx_python_sdk.memory import search_memory as search_memory_fn
from glyx_python_sdk.memory import save_memory as save_memory_fn

logger = logging.getLogger(__name__)

# Define tools for each ComposableAgent
@function_tool
async def use_aider_agent(prompt: str, files: str, model: str = "gpt-5") -> str:
    """Execute Aider for AI-powered code editing and refactoring.

    Args:
        prompt: The task description for Aider
        files: Comma-separated list of files to edit
        model: Model to use (default: gpt-5)

    Returns:
        Result from Aider execution
    """
    logger.info(f"Executing Aider agent: prompt={prompt[:100]}, files={files}")
    agent = ComposableAgent.from_key(AgentKey.AIDER)
    result: AgentResult = await agent.execute(
        {"prompt": prompt, "files": files, "model": model}, timeout=300
    )
    return result.output


@function_tool
async def use_grok_agent(
    prompt: str, model: str = "openrouter/x-ai/grok-code-fast-1"
) -> str:
    """Execute Grok for general reasoning and analysis.

    Args:
        prompt: The question or task for Grok
        model: Model to use (default: grok-code-fast-1)

    Returns:
        Result from Grok execution
    """
    import time

    logger.info(f"Executing Grok agent: prompt={prompt[:100]}")
    start = time.time()
    agent = ComposableAgent.from_key(AgentKey.GROK)
    result: AgentResult = await agent.execute(
        {"prompt": prompt, "model": model}, timeout=300
    )
    duration = time.time() - start
    logger.info(f"Grok execution took {duration:.2f}s")
    return result.output


@function_tool
async def use_claude_agent(prompt: str, model: str = "claude-sonnet-4") -> str:
    """Execute Claude for advanced reasoning and complex workflows.

    Args:
        prompt: The task for Claude
        model: Model to use (default: claude-sonnet-4)

    Returns:
        Result from Claude execution
    """
    logger.info(f"Executing Claude agent: prompt={prompt[:100]}")
    agent = ComposableAgent.from_key(AgentKey.CLAUDE)
    result: AgentResult = await agent.execute(
        {"prompt": prompt, "model": model}, timeout=300
    )
    return result.output


@function_tool
async def use_codex_agent(prompt: str, model: str = "gpt-5") -> str:
    """Execute Codex for code generation.

    Args:
        prompt: Code generation task
        model: Model to use (default: gpt-5)

    Returns:
        Generated code
    """
    logger.info(f"Executing Codex agent: prompt={prompt[:100]}")
    agent = ComposableAgent.from_key(AgentKey.CODEX)
    result: AgentResult = await agent.execute(
        {"prompt": prompt, "model": model}, timeout=300
    )
    return result.output


@function_tool
async def use_opencode_agent(prompt: str, model: str = "gpt-5") -> str:
    """Execute OpenCode for general-purpose coding tasks.

    Args:
        prompt: The coding task
        model: Model to use (default: gpt-5)

    Returns:
        Result from OpenCode execution
    """
    logger.info(f"Executing OpenCode agent: prompt={prompt[:100]}")
    agent = ComposableAgent.from_key(AgentKey.OPENCODE)
    result: AgentResult = await agent.execute(
        {"prompt": prompt, "model": model}, timeout=300
    )
    return result.output


@function_tool
def search_memory(query: str, user_id: str = "glyx_app_1", limit: int = 5) -> str:
    """Search project memory for context.

    Args:
        query: Search query
        user_id: User identifier
        limit: Max results

    Returns:
        JSON string of memories
    """
    return search_memory_fn(query=query, user_id=user_id, limit=limit)


@function_tool
def save_memory(
    content: str,
    agent_id: str,
    run_id: str,
    user_id: str = "glyx_app_1",
    directory_name: str | None = None,
    category: str | None = None,
) -> str:
    """Save memory with metadata.

    Args:
        content: Memory content
        agent_id: Agent identifier
        run_id: Execution run ID
        user_id: User identifier
        directory_name: Project directory
        category: Memory category

    Returns:
        Confirmation message
    """
    return save_memory_fn(
        content=content,
        agent_id=agent_id,
        run_id=run_id,
        user_id=user_id,
        directory_name=directory_name,
        category=category,  # type: ignore
    )


class GlyxOrchestrator:
    """Orchestrator using OpenAI Agents SDK with LiteLLM model backend."""

    def __init__(
        self,
        agent_name: str = "GlyxOrchestrator",
        model: str = "gpt-5",
        mcp_servers: list | None = None,
        session_id: str = "default",
    ):
        self.agent_name = agent_name
        self.model = model
        self.mcp_servers = mcp_servers or []
        self.session_id = session_id
        self.session = SQLiteSession(session_id, "/tmp/glyx_orchestrator.db")

        # Configure LiteLLM model
        litellm_model = LitellmModel(
            model=model,
            api_key=settings.openrouter_api_key,
            api_base="https://openrouter.ai/api/v1",
        )

        # Create orchestrator agent with all tools
        self.agent = Agent(
            name=agent_name,
            model=litellm_model,
            system_prompt="You are an AI orchestrator coordinating specialized agents.",
            tools=[
                use_aider_agent,
                use_grok_agent,
                use_claude_agent,
                use_codex_agent,
                use_opencode_agent,
                search_memory,
                save_memory,
            ],
        )

        self.runner = Runner(
            session=self.session,
        )

    async def run_prompt_streamed_items(self, prompt: str):
        """Run prompt and stream items."""
        async for item in self.runner.run_streamed_items(self.agent, prompt):
            yield item

    async def cleanup(self):
        """Cleanup resources."""
        pass


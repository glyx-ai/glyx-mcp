"""Core orchestrator logic."""

from __future__ import annotations

import logging

from agents import Agent, Runner, SQLiteSession, function_tool
from agents.extensions.models.litellm_model import LitellmModel
from dbos import DBOS

from glyx_python_sdk.composable_agents import ComposableAgent
from glyx_python_sdk.agent_types import AgentKey, AgentResult
from glyx_python_sdk.memory import save_memory as save_memory_fn
from glyx_python_sdk.memory import search_memory as search_memory_fn
from glyx_python_sdk.models.stream_items import stream_item_from_agent
from glyx_python_sdk.settings import settings

logger = logging.getLogger(__name__)


# Define tools for each ComposableAgent - wrapped with @DBOS.step() for checkpointing


@function_tool
@DBOS.step()
async def use_grok_agent(prompt: str, model: str = "openrouter/x-ai/grok-4.1-fast") -> str:
    """Execute Grok for general reasoning and analysis.

    Args:
        prompt: The question or task for Grok
        model: Model to use (default: grok-code-fast-1)

    Returns:
        Result from Grok execution
    """
    import time

    logger.info(f"Executing Grok agent: prompt={prompt[:100]}, model={model}")
    start = time.time()
    agent = ComposableAgent.from_key(AgentKey.GROK)
    result: AgentResult = await agent.execute({"prompt": prompt, "model": model}, timeout=300)
    duration = time.time() - start
    logger.info(f"Grok execution took {duration:.2f}s (model={model})")
    return result.output


@function_tool
@DBOS.step()
async def use_claude_agent(prompt: str, model: str = "claude-sonnet-4") -> str:
    """Execute Claude for advanced reasoning and complex workflows.

    Args:
        prompt: The task for Claude
        model: Model to use (default: claude-sonnet-4)

    Returns:
        Result from Claude execution
    """
    logger.info(f"Executing Claude agent: prompt={prompt[:100]}, model={model}")
    agent = ComposableAgent.from_key(AgentKey.CLAUDE)
    result: AgentResult = await agent.execute({"prompt": prompt, "model": model}, timeout=300)
    return result.output


@function_tool
@DBOS.step()
async def use_codex_agent(prompt: str, model: str = "gpt-5") -> str:
    """Execute Codex for code generation.

    Args:
        prompt: Code generation task
        model: Model to use (default: gpt-5)

    Returns:
        Generated code
    """
    logger.info(f"Executing Codex agent: prompt={prompt[:100]}, model={model}")
    agent = ComposableAgent.from_key(AgentKey.CODEX)
    result: AgentResult = await agent.execute({"prompt": prompt, "model": model}, timeout=300)
    return result.output


@function_tool
@DBOS.step()
async def use_opencode_agent(prompt: str, model: str = "gpt-5") -> str:
    """Execute OpenCode for general-purpose coding tasks.

    Args:
        prompt: The coding task
        model: Model to use (default: gpt-5)

    Returns:
        Result from OpenCode execution
    """
    logger.info(f"Executing OpenCode agent: prompt={prompt[:100]}, model={model}")
    agent = ComposableAgent.from_key(AgentKey.OPENCODE)
    result: AgentResult = await agent.execute({"prompt": prompt, "model": model}, timeout=300)
    return result.output


@function_tool
@DBOS.step()
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
@DBOS.step()
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
        )

        # Create orchestrator agent with all tools
        self.agent = Agent(
            name=agent_name,
            model=litellm_model,
            instructions="You are an AI orchestrator coordinating specialized agents.",
            tools=[
                use_grok_agent,
                use_claude_agent,
                use_codex_agent,
                use_opencode_agent,
                search_memory,
                save_memory,
            ],
        )

    async def run_prompt_streamed_items(self, prompt: str, max_turns: int = 10):
        """Run prompt and stream items."""
        result = Runner.run_streamed(
            starting_agent=self.agent,
            input=prompt,
            session=self.session,
            max_turns=max_turns,
        )
        async for event in result.stream_events():
            if event.type == "run_item_stream_event":
                yield event.item

    async def cleanup(self):
        """Cleanup resources."""
        pass


@DBOS.workflow()
async def run_durable_orchestration(
    prompt: str,
    session_id: str,
    model: str = "openrouter/anthropic/claude-sonnet-4",
    max_turns: int = 10,
) -> None:
    """Durable orchestration workflow with streaming - survives crashes and can be resumed.

    Each agent tool call is checkpointed. On restart, completed steps are skipped.
    Items are streamed via DBOS.write_stream() as they are produced.

    Args:
        prompt: The task prompt
        session_id: Unique session/task ID (used for idempotency)
        model: Model to use for orchestration
        max_turns: Maximum conversation turns
    """
    orch = GlyxOrchestrator(session_id=session_id, model=model)
    async for item in orch.run_prompt_streamed_items(prompt, max_turns=max_turns):
        stream_item = stream_item_from_agent(item)
        DBOS.write_stream("items", stream_item.model_dump())
    DBOS.close_stream("items")

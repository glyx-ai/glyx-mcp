"""Command building functionality for the composable agent system."""

from glyx.tools.load_glyx_configuration import load_glyx_config_impl


def get_orchestration_prompt() -> str:
    """Generate the orchestration prompt with current glyx.json configuration injected."""
    config = load_glyx_config_impl()
    dirs = config["additionalWorkingDirectories"]
    formatted_dirs = "\n".join(f"- {d}" for d in dirs)
    config_section = f"additionalWorkingDirectories:\n{formatted_dirs}"

    return BASE_ORCHESTRATION_PROMPT_TEMPLATE.replace(
        "Current `glyx.json` configuration:\n\n", f"Current `glyx.json` configuration:\n{config_section}\n"
    )


BASE_ORCHESTRATION_PROMPT_TEMPLATE = """
GLYX Orchestrator — Enhanced Multi-Agent Conductor

<ROLE>
You are the GLYX Orchestrator, a specialized AI that manages software development tasks by decomposing user requests, delegating to expert agents and tools, verifying outputs, and integrating results. You NEVER write code yourself—instead, you coordinate others to do so. Focus on parallel execution where possible to maximize efficiency.
</ROLE>

<CORE_PRINCIPLES>
- Decompose tasks into small, verifiable units (≤5 minutes each).
- Delegate liberally: prefer parallelized agents/tools over manual work.
- Verify everything: use tests, linters, and checks before integration.
- Parallelize independent tasks; sequence only when clear dependencies exist.
- Escalate blockers immediately with diagnosis and proposals.
</CORE_PRINCIPLES>

<CONFIGURATION>
Load and inject `glyx.json` dynamically using `load_glyx_config`. This includes additional working directories for multi-project management.

Current configuration:
additionalWorkingDirectories:
- ~/bldrbase/
</CONFIGURATION>

<CODING_AGENTS>
- Claude 4 Opus (Deep Thinker): For architecture, debugging, security, reviews.
- Gemini (Speed Drafter): For tests, docs, boilerplate.
- Aider (Contextual Coder): For small edits, quick fixes.
- Codex (Generalist Coder): For implementations, balanced tasks.
- Grok 4 (Researcher): For complex analysis, cutting-edge tasks -- similar to Claude 4 Opus and GPT-5.
- GPT-5 (Deep Researcher): For complex analysis, cutting-edge tasks -- similar to Claude 4 Opus and Grok-4.
</CODING_AGENTS>

<OPERATING_PROCEDURE>
1. **Understand**: Analyze request, identify goals/sub-goals. Gather context via tools/agents if needed.
2. **Decompose**: Break into micro-tasks with dependencies noted.
3. **Route & Delegate**: Use decision matrix; issue precise instructions.
4. **Verify**: Run checks (e.g., `make test`, linters); re-delegate if failed.
5. **Integrate**: Apply verified changes to filesystem.
6. **Report**: Summarize changes, status, next steps.
</OPERATING_PROCEDURE>

<DECISION_MATRIX>
- Simple edit: Aider.
- Quick generation: Choose between Gemini and Grok.
- Feature implementation: Consensus architecture plan, subtask breakdown, and delegation to the appropriate agents.
- Complex analysis or research: Claude 4 Opus, GPT-5, and Grok-4.
If >1 task: Parallelize non-dependent ones.
</DECISION_MATRIX>

<ERROR_RECOVERY>
- **Level 1**: Retry with clarified prompt if you originally misunderstood. Do not waste time retrying if the error is not due to misunderstanding.
- **Level 2**: Escalate to human with goal, attempts, error details, proposals.
</ERROR_RECOVERY>

<IMAGE_HANDLING>
Enumerate images, extract details, tie to goal. Clarify minimally; assume when possible.
</IMAGE_HANDLING>

<SESSION_MEMORY>
Track modifications, patterns, agent performance, user preferences. You can access memories via the `session_memory` MCP server -- which
you should use to store and retrieve relevant information as needed.
</SESSION_MEMORY>
""".strip()



"""
Enhanced Unified Coding Agent with MCP Server Integration
Combines traditional coding agents with MCP server capabilities
"""

from __future__ import annotations

import logging
from pathlib import Path

from agents import (
    Agent,
    MessageOutputItem,
    ReasoningItem,
    RunConfig,
    Runner,
    SQLiteSession,
    Session,
    Tool,
    ToolCallItem,
    ToolCallOutputItem,
)
from agents.extensions.models.litellm_model import LitellmModel
from agents.mcp import MCPServer

from glyx.adapters.mem0_milvus_session import Mem0MilvusSession
from glyx.config.prompts import get_orchestration_prompt
from glyx.config.settings import settings

logger = logging.getLogger(__name__)


class GlyxOrchestrator:
    """Unified orchestrator that owns agents, MCP servers, and session."""

    def __init__(
        self,
        agent_name: str,
        model: str,
        tools: list[Tool] | None = None,
        mcp_servers: list[MCPServer] | None = None,
        session_id: str = "default",
    ):
        if tools is None:
            tools = []
        self.agent_name = agent_name
        self.model = model
        self.tools = tools
        self.mcp_servers = mcp_servers
        self.agent = None
        self.session = None
        self.session_id = session_id

        logger.info("Configured MCP servers: %s", [s.name for s in self.mcp_servers or []])

    async def run_prompt_streamed_items(self, text: str):
        """Run a prompt through the agent and stream only the new items.

        Returns an async generator that yields only the new items (messages, tool calls, etc).

        Example usage:
            async for item in orchestrator.run_prompt_streamed_items("Hello"):
                print(item)
        """
        # Initialize agent and session if not already initialized
        if not self.agent:
            # Use LiteLLM model for flexibility across providers
            litellm_model = LitellmModel(
                model=self.model,
                api_key=settings.openrouter_api_key,
                base_url=settings.OPENROUTER_BASE_URL,
            )

            self.agent = Agent(
                name=self.agent_name,
                model=litellm_model,
                tools=self.tools,
                mcp_servers=self.mcp_servers,
                instructions=get_orchestration_prompt(),
            )

            # Connect MCP servers with error handling
            connected_servers = []
            for server in self.agent.mcp_servers:
                try:
                    await server.connect()
                    logger.info(f"Connected MCP server: {server.name}")
                    connected_servers.append(server.name)
                except Exception as e:
                    logger.exception(f"Failed to connect MCP server {server.name}: {e}")

            if connected_servers:
                logger.info(f"Successfully connected to MCP servers: {connected_servers}")
            else:
                logger.warning("No MCP servers connected successfully")

            # Use Mem0MilvusSession with Zilliz Cloud or localhost
            db_path = settings.zilliz_uri or "localhost:19530"
            token = settings.zilliz_api_key
            self.session = Mem0MilvusSession(
                session_id=self.session_id,
                db_path=db_path,
                token=token
            )
            logger.info(f"Session created with Mem0/Milvus backend for session_id: {self.session_id}")

        result = Runner.run_streamed(
            starting_agent=self.agent,
            input=text,
            session=self.session,
            run_config=RunConfig(model_provider=settings.get_model_provider()),
            max_turns=settings.orchestrator_max_turns,
        )

        async for event in result.stream_events():
            if event.type == "run_item_stream_event":
                item = event.item

                # Yield only the specific item types we support
                if isinstance(item, MessageOutputItem | ToolCallItem | ToolCallOutputItem | ReasoningItem):
                    yield item

    async def clear_session(self) -> None:
        if self.session:
            await self.session.clear_session()
            logger.info("Session cleared.")

    async def cleanup(self) -> None:
        if self.agent and self.agent.mcp_servers:
            for server in self.agent.mcp_servers:
                try:
                    await server.cleanup()
                    logger.info(f"Cleaned up MCP server: {server.name}")
                except Exception as e:
                    logger.warning(f"Error cleaning up MCP server {server.name}: {e}")

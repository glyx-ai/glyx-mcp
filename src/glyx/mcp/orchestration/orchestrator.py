"""Orchestrator agent for coordinating multiple ComposableAgents using OpenAI Agents SDK."""

from __future__ import annotations

import logging
import uuid

from agents import Agent, ModelSettings, Runner, function_tool
from fastmcp import Context
from pydantic import BaseModel, Field

from glyx.mcp.composable_agent import AgentKey, AgentResult, ComposableAgent
from glyx.tasks.models.task import Task
from glyx.mcp.orchestration.prompts import get_orchestrator_instructions, get_memory_saver_instructions
from glyx.mcp.settings import settings
from glyx.mcp.tools.use_memory import search_memory as search_memory_fn
from glyx.mcp.tools.use_memory import save_memory as save_memory_fn
from glyx.tasks.tools.task_tools import assign_task as assign_task_fn
from glyx.tasks.tools.task_tools import create_task as create_task_fn
from glyx.tasks.tools.task_tools import update_task as update_task_fn

logger = logging.getLogger(__name__)

# Realtime broadcasting
from glyx.mcp.realtime import broadcast_event
# Generate task schema once at module load
TASK_JSON_SCHEMA = Task.model_json_schema()


class OrchestratorResult(BaseModel):
    """Result from orchestrator execution."""

    success: bool = Field(..., description="Whether orchestration succeeded")
    output: str = Field(..., description="Final synthesized response from the orchestrator")
    tool_calls: list[str] = Field(default_factory=list, description="List of tools/agents called during execution")
    error: str | None = Field(None, description="Error message if orchestration failed")


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
    result: AgentResult = await agent.execute({"prompt": prompt, "files": files, "model": model}, timeout=300)
    return result.output


@function_tool
async def use_grok_agent(prompt: str, model: str = "openrouter/x-ai/grok-code-fast-1") -> str:
    """Execute Grok for general reasoning and analysis.

    Args:
        prompt: The question or task for Grok
        model: Model to use (default: grok-code-fast-1)

    Returns:
        Result from Grok execution
    """
    import time
    start = time.time()
    logger.info(f"[GROK START] Executing Grok agent: prompt={prompt[:100]}")

    agent_load_start = time.time()
    agent = ComposableAgent.from_key(AgentKey.GROK)
    logger.info(f"[GROK AGENT LOADED] Took {time.time() - agent_load_start:.2f}s")

    execute_start = time.time()
    logger.info(f"[GROK EXECUTE START] Calling agent.execute with timeout=60")
    result: AgentResult = await agent.execute({"prompt": prompt, "model": model}, timeout=60)
    logger.info(f"[GROK EXECUTE DONE] Took {time.time() - execute_start:.2f}s, exit_code={result.exit_code}")

    output_len = len(result.output)
    logger.info(f"[GROK COMPLETE] Total time: {time.time() - start:.2f}s, output length: {output_len}")

    return result.output


@function_tool
async def use_codex_agent(prompt: str, model: str = "gpt-5") -> str:
    """Execute Codex for code generation.

    Args:
        prompt: The coding task for Codex
        model: Model to use (default: gpt-5)

    Returns:
        Result from Codex execution
    """
    logger.info(f"Executing Codex agent: prompt={prompt[:100]}")
    agent = ComposableAgent.from_key(AgentKey.CODEX)
    result: AgentResult = await agent.execute({"prompt": prompt, "model": model}, timeout=300)
    return result.output


@function_tool
async def use_claude_agent(prompt: str, model: str = "claude-sonnet-4-20250514", max_turns: int = 30) -> str:
    """Execute Claude Code for complex coding tasks.

    Args:
        prompt: The task for Claude
        model: Model to use (default: claude-sonnet-4)
        max_turns: Maximum conversation turns

    Returns:
        Result from Claude execution
    """
    logger.info(f"Executing Claude agent: prompt={prompt[:100]}")
    agent = ComposableAgent.from_key(AgentKey.CLAUDE)
    result: AgentResult = await agent.execute({"prompt": prompt, "model": model, "max_turns": max_turns}, timeout=600)
    return result.output


@function_tool
async def use_opencode_agent(prompt: str) -> str:
    """Execute OpenCode CLI for various tasks.

    Args:
        prompt: The task for OpenCode

    Returns:
        Result from OpenCode execution
    """
    logger.info(f"Executing OpenCode agent: prompt={prompt[:100]}")
    agent = ComposableAgent.from_key(AgentKey.OPENCODE)
    result: AgentResult = await agent.execute({"prompt": prompt}, timeout=300)
    return result.output


# Wrap memory functions as function_tools (direct wrapping)
search_memory = function_tool(search_memory_fn)
save_memory = function_tool(save_memory_fn)

# Wrap task tracking functions as function_tools
create_task = function_tool(create_task_fn)
assign_task = function_tool(assign_task_fn)
update_task = function_tool(update_task_fn)


class Orchestrator:
    """Orchestrates multiple AI agents using OpenAI Agents SDK."""

    ctx: Context
    agent: Agent

    def __init__(self, ctx: Context, model: str | None = None) -> None:
        """Initialize orchestrator with OpenAI Agents SDK.

        Args:
            ctx: FastMCP context for progress reporting (required)
            model: Model to use for orchestration (defaults to settings)
        """
        self.ctx = ctx
        orchestrator_model = model or settings.default_orchestrator_model

        # Format instructions with task schema
        import json
        task_schema_str = json.dumps(TASK_JSON_SCHEMA, indent=2)

        # Create ask_user tool with access to ctx
        @function_tool
        async def ask_user(question: str, expected_format: str = "free-form text") -> str:
            """Ask the user a clarifying question and wait for their response.

            Use this when you need additional information to properly orchestrate the task.
            Examples:
            - Ambiguous requirements that could be interpreted multiple ways
            - Need to know which files/directories to focus on
            - Missing information about constraints or preferences
            - Unclear priority or scope

            Args:
                question: The question to ask the user (be specific and clear)
                expected_format: Description of the expected response format (e.g., "file paths", "yes/no", "priority level")

            Returns:
                The user's response as a string, or a structured prompt for Claude Code to use AskUserQuestion
            """
            logger.info(f"Orchestrator asking user: {question}")

            # Format the full message
            full_message = f"{question}\n\nPlease provide: {expected_format}"

            # Simple string response type
            class UserResponse(BaseModel):
                answer: str = Field(..., description=f"Your response ({expected_format})")

            try:
                response = await ctx.elicit(message=full_message, response_type=UserResponse)

                if hasattr(response, "data") and hasattr(response.data, "answer"):
                    answer = response.data.answer
                    logger.info(f"User answered: {answer}")
                    return answer
                else:
                    logger.warning("User declined or cancelled the question - returning structured prompt for AskUserQuestion")
                    # Return a structured signal that tells the orchestrator to format this as an AskUserQuestion request
                    return f"[NEEDS_STRUCTURED_QUESTION]\nQuestion: {question}\nExpected Format: {expected_format}"
            except Exception as e:
                logger.warning(f"Elicitation failed: {e} - returning structured prompt for AskUserQuestion")
                # Return a structured signal that tells the orchestrator to format this as an AskUserQuestion request
                return f"[NEEDS_STRUCTURED_QUESTION]\nQuestion: {question}\nExpected Format: {expected_format}"

        # Get orchestrator instructions with task schema injected
        instructions = get_orchestrator_instructions(task_schema_str)

        # Define the orchestrator agent with all available tools
        self.agent = Agent(
            name="Orchestrator",
            instructions=instructions,
            model=orchestrator_model,
            tools=[
                ask_user,  # Interactive clarification
                use_aider_agent,
                use_grok_agent,
                use_codex_agent,
                use_claude_agent,
                use_opencode_agent,
                search_memory,
                save_memory,
                create_task,
                assign_task,
                update_task,
            ],
        )

    async def orchestrate(self, task: str) -> OrchestratorResult:
        """Orchestrate execution of a complex task using multiple agents.

        Args:
            task: The user's task description

        Returns:
            OrchestratorResult with final output
        """
        try:
            await broadcast_event("orchestrator.start", {"task_preview": task[:200]})
            await self.ctx.report_progress(progress=0, total=100, message="Starting orchestration...")
            await self.ctx.info(f"🎯 Orchestrating task: {task}")

            logger.info(f"Orchestrating task: {task}")

            # Track execution details for rich output
            tool_calls = []
            agent_updates = []

            # Run the orchestrator agent with streaming
            logger.info("Starting streaming orchestration")
            result = Runner.run_streamed(
                self.agent,
                input=task,
            )

            # Process stream events
            async for event in result.stream_events():
                if event.type == "run_item_stream_event":
                    item = event.item
                    if item.type == "tool_call_item":
                        tool_name = item.raw_item.name
                        tool_calls.append(tool_name)
                        logger.info(f"Tool called: {tool_name}")
                        await self.ctx.info(f"🔧 Calling agent: {tool_name}")
                        await broadcast_event("orchestrator.tool_call", {"tool": tool_name})
                    elif item.type == "message_output_item":
                        logger.info(f"Message output received")

                elif event.type == "agent_updated_stream_event":
                    agent_name = event.new_agent.name
                    agent_updates.append(agent_name)
                    logger.info(f"Agent updated: {agent_name}")
                    await self.ctx.info(f"🤖 Agent: {agent_name}")
                    await broadcast_event("orchestrator.agent_updated", {"agent": agent_name})

            # Get final output (no await needed - already consumed stream)
            output = result.final_output

            logger.info(f"Orchestration complete. Tool calls: {len(tool_calls)}")
            await self.ctx.report_progress(progress=90, total=100, message="Saving memories to graph...")
            await broadcast_event("orchestrator.complete", {"tool_calls": tool_calls, "agent_updates": agent_updates})

            # FORCE memory saving after orchestration
            run_id = str(uuid.uuid4())
            await self._force_memory_save(task=task, output=output, tool_calls=tool_calls, run_id=run_id)

            await self.ctx.report_progress(progress=100, total=100, message="Orchestration complete")
            await self.ctx.info("✅ Orchestration completed successfully")

            return OrchestratorResult(success=True, output=output, tool_calls=tool_calls, error=None)
        except Exception as e:
            logger.error(f"Orchestration failed: {e}")
            await broadcast_event("orchestrator.error", {"error": str(e)})
            return OrchestratorResult(success=False, output="", tool_calls=[], error=str(e))

    async def _force_memory_save(
        self, task: str, output: str, tool_calls: list[str], run_id: str
    ) -> None:
        """Force memory saving with a dedicated agent that MUST call save_memory.

        This ensures every orchestration saves memories to the graph.

        Args:
            task: Original user task
            output: Orchestration output
            tool_calls: List of tools that were called
            run_id: Unique run identifier
        """
        logger.info("Creating memory saver agent with forced tool call")
        await self.ctx.info("💾 Saving key learnings to memory graph...")

        # Create memory saver agent that MUST call save_memory
        memory_saver = Agent(
            name="MemorySaver",
            instructions=get_memory_saver_instructions(),
            model=settings.default_orchestrator_model,
            tools=[save_memory],
            model_settings=ModelSettings(
                tool_choice="save_memory",  # FORCE this specific tool
            ),
        )

        # Prepare context for memory saver
        context = f"""
Task: {task}

Output Summary: {output[:500]}...

Tools Used: {", ".join(tool_calls)}

Your job: Extract and save 1-3 key memories from this orchestration.
Save architectural decisions, patterns discovered, file locations, technical decisions, or important concepts.
Call save_memory for EACH distinct memory (architecture, integration, code style, etc.).
"""

        try:
            # Run memory saver - it MUST call save_memory due to tool_choice
            logger.info("Running memory saver agent (forced tool call)")
            result = Runner.run_streamed(memory_saver, input=context)

            # Process stream events to track memory saves
            memory_count = 0
            async for event in result.stream_events():
                if event.type == "run_item_stream_event":
                    item = event.item
                    if item.type == "tool_call_item" and hasattr(item.raw_item, "name") and item.raw_item.name == "save_memory":  # type: ignore[union-attr]
                        memory_count += 1
                        logger.info(f"Memory save #{memory_count} triggered")

            logger.info(f"Memory saver completed. Saved {memory_count} memories.")
            await self.ctx.info(f"💾 Saved {memory_count} memories to graph")
            await broadcast_event("orchestrator.memory_saver.complete", {"saved": memory_count})

        except Exception as e:
            logger.error(f"Memory saving failed: {e}")
            await self.ctx.warning(f"⚠️ Memory saving encountered an error: {e}")
            await broadcast_event("orchestrator.memory_saver.error", {"error": str(e)})

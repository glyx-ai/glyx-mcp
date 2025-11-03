"""Orchestrator agent for coordinating multiple ComposableAgents using OpenAI Agents SDK."""

from __future__ import annotations

import logging
from typing import Any

from agents import Agent, Runner, function_tool
from fastmcp import Context
from langfuse import get_client
from pydantic import BaseModel, Field

from glyx_mcp.composable_agent import AgentKey, AgentResult, ComposableAgent
from glyx_mcp.settings import settings
from glyx_mcp.tools.use_memory import search_memory as search_memory_fn
from glyx_mcp.tools.use_memory import save_memory as save_memory_fn

logger = logging.getLogger(__name__)


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


# Memory metadata model for strict schema compliance
class MemoryMetadata(BaseModel):
    """Metadata for memory storage."""
    directory_name: str | None = None
    category: str | None = None
    user_intention: str | None = None


# Wrap memory functions as function_tools
@function_tool
def search_memory(query: str, user_id: str = "glyx_app_1", limit: int = 5) -> str:
    """Search past conversations and project context from memory."""
    return search_memory_fn(query=query, user_id=user_id, limit=limit)


@function_tool
def save_memory(
    messages: str,
    agent_id: str | None = None,
    user_id: str = "glyx_app_1",
    metadata: MemoryMetadata | None = None,
) -> str:
    """Save structured memory with metadata and context."""
    metadata_dict = metadata.model_dump() if metadata else None
    return save_memory_fn(messages=messages, agent_id=agent_id, user_id=user_id, metadata=metadata_dict)


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

        # Define the orchestrator agent with all available tools
        self.agent = Agent(
            name="Orchestrator",
            instructions="""You are a coding-focused AI orchestrator that coordinates specialized agents to accomplish software engineering tasks while maintaining deep project memory.

CORE ROLE & RESPONSIBILITIES:
You are a COORDINATOR and DELEGATOR, not a doer. Your job is to:
1. Understand the user's request
2. Search memory for relevant context
3. Delegate work to specialized agents
4. Synthesize results into coherent responses
5. Save important outcomes to memory

CRITICAL: You should ALMOST NEVER do extensive research, analysis, or code exploration yourself.
Delegate all substantial work to specialized agents. Your value is in orchestration, not execution.
Keep your own work minimal - let agents do the heavy lifting.

CORE MISSION:
Your primary purpose is to help build and maintain software projects with continuity and context. Memory about code architecture, technical decisions, patterns, and project structure is CRITICAL. Every interaction should build upon past context to create a coherent, consistent codebase.

AVAILABLE CODING AGENTS:
- use_aider_agent: AI pair programmer (requires 'prompt' and 'files' params)
- use_grok_agent: Fast reasoning and analysis
- use_codex_agent: Code generation
- use_claude_agent: Complex multi-step workflows
- use_opencode_agent: General-purpose OpenCode CLI

MEMORY SYSTEM (CRITICAL):
- search_memory: Query project memory before every task - find relevant architecture, patterns, decisions, file locations
- save_memory: Rich memory storage with full metadata and context

save_memory STRUCTURE:
```python
save_memory(
    messages: str | list[dict[str, str]],  # Content or conversation messages
    agent_id: str | None = None,           # "orchestrator", "aider", "grok", "codex", "claude"
    user_id: str = "glyx_app_1",         # User identifier
    metadata: dict[str, Any] | None = None,  # {"directory_name": "...", "category": "...", "user_intention": "..."}
    run_id: str | None = None,             # Unique run identifier
    timestamp: int | None = None,          # Unix timestamp
)
```

METADATA CATEGORIES (use in metadata["category"]):
- "architecture": System design, component structure, design patterns
- "integrations": How systems connect, MCP tools, SDK integrations, APIs
- "code_style_guidelines": Project conventions, coding style, naming patterns
- "project_id": Project identity, purpose, core mission
- "observability": Logging, tracing, monitoring, debugging approaches
- "product": Product features, user-facing functionality
- "key_concept": Important concepts, patterns, paradigms

FEW-SHOT EXAMPLES:

Example 1 - Architecture Decision:
```python
save_memory(
    messages="Project uses OpenAI Agents SDK for orchestration with Runner.run_streamed() for parallel agent execution",
    agent_id="orchestrator",
    metadata={
        "directory_name": "glyx-mcp",
        "category": "architecture",
        "user_intention": "understand_architecture"
    }
)
```

Example 2 - Integration Pattern:
```python
save_memory(
    messages="Mem0 memory integration uses enable_graph=True for all operations to create entity relationships. Custom categories configured: architecture, integrations, code_style_guidelines, project_id, observability, product, key_concept",
    agent_id="orchestrator",
    metadata={
        "directory_name": "glyx-mcp",
        "category": "integrations",
        "user_intention": "add_feature"
    }
)
```

Example 3 - Code Style:
```python
save_memory(
    messages="Project uses Pydantic models for all configs and structured data. Strict mypy mode enabled. All agent execution is async with asyncio.",
    agent_id="aider",
    metadata={
        "directory_name": "glyx-mcp",
        "category": "code_style_guidelines",
        "user_intention": "refactor"
    }
)
```

Example 4 - File Location:
```python
save_memory(
    messages="Agent configurations stored in src/glyx_mcp/config/*.json. Each agent has AgentConfig with command, args structure. ComposableAgent in composable_agent.py handles execution.",
    agent_id="orchestrator",
    metadata={
        "directory_name": "glyx-mcp",
        "category": "architecture",
        "user_intention": "understand_codebase"
    }
)
```

Example 5 - Observability:
```python
save_memory(
    messages="Langfuse instrumentation enabled for all orchestrator executions. OpenAI Agents instrumented via OpenAIAgentsInstrumentor(). Logs use Python logging with DEBUG level.",
    agent_id="orchestrator",
    metadata={
        "directory_name": "glyx-mcp",
        "category": "observability",
        "user_intention": "debug_issue"
    }
)
```

MEMORY PRIORITIES (What to save/search):
1. **Architecture & Design**: Component structure, module organization, design patterns used
2. **Technical Decisions**: Why certain approaches were chosen, trade-offs considered, alternatives rejected
3. **Code Patterns**: Project conventions, coding style, naming patterns, file organization
4. **File Locations**: Where specific features/components live, key file paths
5. **User Preferences**: Coding style preferences, preferred tools/libraries, testing approaches
6. **Past Solutions**: How similar problems were solved, bugs fixed, refactorings done
7. **Project Context**: Tech stack, dependencies, constraints, performance considerations

ORCHESTRATION WORKFLOW:

1. RECALL CONTEXT (ALWAYS FIRST):
   - Search memory with queries about: the task domain, related features, similar past work
   - Example queries: "authentication implementation", "API patterns", "testing approach", "file structure"
   - Use retrieved context to inform delegation decisions

2. DELEGATE (DON'T DO IT YOURSELF):
   - Break down the task and identify which agent(s) should handle each part
   - Choose the right agent(s) for each subtask based on their capabilities
   - Run independent delegations in parallel when possible (the SDK handles this automatically)
   - Your job is to coordinate, not to do the research/coding yourself

3. SYNTHESIZE AGENT RESULTS:
   - Combine outputs from multiple agents into a coherent response
   - Reference past context when relevant
   - Explain how the solution fits with existing project patterns

4. PERSIST KNOWLEDGE:
   - Save architectural decisions: "Decided to use X pattern for Y because Z"
   - Save file locations: "User authentication implemented in src/auth/user.py"
   - Save patterns: "Project uses Pydantic models for all config validation"
   - Save preferences: "User prefers async/await over callbacks"
   - Save solutions: "Fixed bug X by doing Y"

CRITICAL RULES:
- ALWAYS search memory before starting a task - context is everything in software projects
- ALWAYS delegate research and coding work to specialized agents - don't do it yourself
- ALWAYS save important technical decisions, patterns, and file locations to memory
- Maintain consistency with past architectural decisions unless explicitly asked to change
- Reference past context in your responses to show continuity
- Be efficient: only delegate to agents that add value to the task

EXAMPLE MEMORY USAGE:
Task: "Add user authentication"
1. Search: "authentication", "user management", "security patterns"
2. Recall: "Project uses JWT tokens, auth in src/auth/, Pydantic validation everywhere"
3. Execute: Use aider to add auth endpoint following existing patterns
4. Save: "Added JWT authentication to /api/login endpoint in src/api/auth.py, follows existing Pydantic validation pattern"

Your goal: Build software with an AI that REMEMBERS and maintains architectural coherence across all interactions.""",
            model=orchestrator_model,
            tools=[
                use_aider_agent,
                use_grok_agent,
                use_codex_agent,
                use_claude_agent,
                use_opencode_agent,
                search_memory,
                save_memory,
            ],
        )

    async def orchestrate(self, task: str) -> OrchestratorResult:
        """Orchestrate execution of a complex task using multiple agents.

        Args:
            task: The user's task description

        Returns:
            OrchestratorResult with final output
        """
        langfuse = get_client()
        try:
            with langfuse.start_as_current_span(name="orchestrator_execution") as span:
                span.update(input={"task": task})

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
                        elif item.type == "message_output_item":
                            logger.info(f"Message output received")

                    elif event.type == "agent_updated_stream_event":
                        agent_name = event.new_agent.name
                        agent_updates.append(agent_name)
                        logger.info(f"Agent updated: {agent_name}")
                        await self.ctx.info(f"🤖 Agent: {agent_name}")

                # Get final output (no await needed - already consumed stream)
                output = result.final_output

                logger.info(f"Orchestration complete. Tool calls: {len(tool_calls)}")

                await self.ctx.report_progress(progress=100, total=100, message="Orchestration complete")
                await self.ctx.info("✅ Orchestration completed successfully")

                span.update(output={"output": output, "tool_calls": tool_calls})

                return OrchestratorResult(success=True, output=output, tool_calls=tool_calls, error=None)
        except Exception as e:
            logger.error(f"Orchestration failed: {e}")
            return OrchestratorResult(success=False, output="", tool_calls=[], error=str(e))

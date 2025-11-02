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

logger = logging.getLogger(__name__)


class OrchestratorResult(BaseModel):
    """Result from orchestrator execution."""

    success: bool = Field(..., description="Whether orchestration succeeded")
    output: str = Field(..., description="Final synthesized response from the orchestrator")
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
async def use_grok_agent(prompt: str, model: str = "openrouter/x-ai/grok-4-fast") -> str:
    """Execute Grok for general reasoning and analysis.

    Args:
        prompt: The question or task for Grok
        model: Model to use (default: grok-4-fast)

    Returns:
        Result from Grok execution
    """
    logger.info(f"Executing Grok agent: prompt={prompt[:100]}")
    agent = ComposableAgent.from_key(AgentKey.GROK)
    result: AgentResult = await agent.execute({"prompt": prompt, "model": model}, timeout=300)
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
            instructions="""You are an AI orchestrator that coordinates multiple specialized agents to accomplish complex tasks.

AVAILABLE AGENTS (as tools):
- use_aider_agent: AI-powered code editing, refactoring, file modifications (requires 'prompt' and 'files' parameters)
- use_grok_agent: General reasoning, analysis, question-answering
- use_codex_agent: Code generation and execution
- use_claude_agent: Complex coding tasks, multi-turn workflows
- use_opencode_agent: OpenCode CLI integration for various models

YOUR APPROACH:
1. Analyze the user's task carefully
2. Determine which agents are needed and in what order
3. Call the appropriate agent tools with the right parameters
4. Synthesize the results from multiple agents into a coherent final response

IMPORTANT:
- For code editing tasks, always use use_aider_agent with both 'prompt' and 'files' parameters
- Break down complex tasks into simpler subtasks for individual agents
- Consider the order of execution - some tasks may depend on others
- Always provide a final synthesis that directly answers the user's original request

Be efficient: only use the agents that are truly necessary.""",
            model=orchestrator_model,
            tools=[
                use_aider_agent,
                use_grok_agent,
                use_codex_agent,
                use_claude_agent,
                use_opencode_agent,
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
        with langfuse.start_as_current_span(name="orchestrator_execution") as span:
            span.update(input={"task": task})

            logger.info(f"DEBUG: About to report progress - Starting orchestration")
            await self.ctx.report_progress(progress=0, total=100, message="Starting orchestration...")

            logger.info(f"DEBUG: About to send info message")
            await self.ctx.info(f"Orchestrating task: {task}")

            logger.info(f"Orchestrating task: {task}")

            # Run the orchestrator agent
            logger.info(f"DEBUG: About to run orchestrator agent")
            result = await Runner.run(
                self.agent,
                input=task,
            )

            output = result.final_output
            logger.info(f"DEBUG: Got output: {output[:100]}")

            await self.ctx.report_progress(progress=100, total=100, message="Orchestration complete")
            await self.ctx.info("✓ Orchestration completed successfully")
            await self.ctx.info(f"DEBUG OUTPUT: {output}")

            span.update(output={"output": output})

            return OrchestratorResult(success=True, output=output, error=None)

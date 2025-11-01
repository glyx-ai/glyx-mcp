"""Orchestrator agent for coordinating multiple ComposableAgents using GPT-5."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from langfuse import get_client
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from glyx_mcp.composable_agent import AgentKey, AgentResult, ComposableAgent

logger = logging.getLogger(__name__)


class AgentTask(BaseModel):
    """A task to be executed by a specific agent."""

    agent: str = Field(..., description="Agent name (e.g., 'aider', 'grok', 'codex')")
    task_description: str = Field(..., description="What the agent should do")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Parameters to pass to the agent")


class ExecutionPlan(BaseModel):
    """Plan for executing multiple agents in sequence."""

    reasoning: str = Field(..., description="Why this plan was chosen")
    tasks: list[AgentTask] = Field(..., description="Ordered list of agent tasks to execute")


class OrchestratorResult(BaseModel):
    """Result from orchestrator execution."""

    success: bool = Field(..., description="Whether orchestration succeeded")
    plan: ExecutionPlan | None = Field(None, description="The execution plan that was created")
    agent_results: list[dict[str, Any]] = Field(default_factory=list, description="Results from each agent")
    synthesis: str = Field(..., description="Final synthesized response")
    error: str | None = Field(None, description="Error message if orchestration failed")


class Orchestrator:
    """Orchestrates multiple AI agents using GPT-5 for planning and coordination."""

    api_key: str
    client: AsyncOpenAI
    model: str
    available_agents: list[str]

    def __init__(self, api_key: str | None = None, model: str = "gpt-5") -> None:
        """Initialize orchestrator with OpenAI client.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Model to use for orchestration planning (default: gpt-5)
        """
        resolved_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError("OPENAI_API_KEY environment variable must be set")

        self.api_key = resolved_key
        self.client = AsyncOpenAI(api_key=self.api_key)
        self.model = model
        self.available_agents = self._discover_agents()

    def _discover_agents(self) -> list[str]:
        """Discover all available agent configurations."""
        # Get all agent keys from the enum
        return [agent.value for agent in AgentKey]

    async def _create_plan(self, task: str) -> ExecutionPlan:
        """Use GPT-5 to analyze task and create execution plan.

        Args:
            task: The user's task description

        Returns:
            ExecutionPlan with ordered agent tasks
        """
        langfuse = get_client()
        with langfuse.start_as_current_generation(name="plan_creation", model=self.model) as generation:
            generation.update(input={"task": task})

            system_prompt = """You are an AI orchestrator that coordinates multiple specialized agents.

AVAILABLE AGENTS AND THEIR CAPABILITIES:
- aider: AI-powered code editing, refactoring, file modifications (requires 'files' parameter)
- grok: General reasoning, analysis, question-answering via OpenCode CLI
- codex: Code generation and execution with GPT models
- gemini: Google's Gemini model for various tasks
- claude: Complex coding tasks, multi-turn workflows (Claude Code CLI)
- opencode: OpenCode CLI integration for various models
- deepseek_r1: DeepSeek R1 reasoning model
- kimi_k2: KIMI K2 model capabilities

YOUR TASK:
Analyze the user's task and create an execution plan that specifies:
1. Which agents are needed (in order)
2. What each agent should do
3. What parameters each agent needs

Return your plan as JSON with this structure:
{{
  "reasoning": "Why you chose this approach",
  "tasks": [
    {{
      "agent": "agent_name",
      "task_description": "What this agent should do",
      "parameters": {{"param": "value"}}
    }}
  ]
}}

IMPORTANT PARAMETERS:
- aider requires: "prompt" and "files" (comma-separated file paths)
- grok requires: "prompt"
- codex requires: "prompt"
- All agents support optional "model" parameter

Keep the plan simple and efficient. Only use agents that are truly needed."""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"TASK: {task}"},
                ],
                response_format={"type": "json_object"},
            )

            # Parse response
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from GPT-5")

            plan_data = json.loads(content)
            plan = ExecutionPlan.model_validate(plan_data)

            # Log the full plan
            logger.info(f"Execution plan reasoning: {plan.reasoning}")
            for i, agent_task in enumerate(plan.tasks, 1):
                logger.info(
                    f"Task {i}: agent={agent_task.agent}, "
                    f"description={agent_task.task_description}, params={agent_task.parameters}"
                )

            generation.update(output={"plan": plan.model_dump()})
            return plan

    async def _execute_agent_task(self, agent_task: AgentTask) -> dict[str, Any]:
        """Execute a single agent task.

        Args:
            agent_task: The task specification

        Returns:
            Dictionary with agent result details
        """
        try:
            # Validate agent exists
            agent_key = AgentKey(agent_task.agent)
        except ValueError:
            logger.error(f"Unknown agent: {agent_task.agent}")
            return {
                "agent": agent_task.agent,
                "success": False,
                "error": f"Unknown agent: {agent_task.agent}",
                "output": "",
            }

        # Create agent and execute
        try:
            logger.info(f"Creating agent '{agent_task.agent}' with parameters: {agent_task.parameters}")
            agent = ComposableAgent.from_key(agent_key)
            result: AgentResult = await agent.execute(agent_task.parameters, timeout=300)

            # Log detailed execution results
            logger.info(f"Agent '{agent_task.agent}' execution completed:")
            logger.info(f"  Command: {result.command}")
            logger.info(f"  Exit code: {result.exit_code}")
            logger.info(f"  Execution time: {result.execution_time:.2f}s")
            logger.info(f"  Success: {result.success}")
            logger.info(f"  Stdout: {result.stdout[:500]}")  # First 500 chars
            if result.stderr:
                logger.warning(f"  Stderr: {result.stderr[:500]}")

            return {
                "agent": agent_task.agent,
                "task": agent_task.task_description,
                "success": result.success,
                "output": result.output,
                "exit_code": result.exit_code,
                "execution_time": result.execution_time,
                "error": result.stderr if not result.success else None,
            }
        except Exception as e:
            logger.error(f"Error executing {agent_task.agent}: {e}", exc_info=True)
            return {
                "agent": agent_task.agent,
                "task": agent_task.task_description,
                "success": False,
                "error": str(e),
                "output": "",
            }

    async def _synthesize_results(
        self, original_task: str, plan: ExecutionPlan, agent_results: list[dict[str, Any]]
    ) -> str:
        """Use GPT-5 to synthesize results from multiple agents into a coherent response.

        Args:
            original_task: The original user task
            plan: The execution plan that was used
            agent_results: Results from all agent executions

        Returns:
            Synthesized response string
        """
        langfuse = get_client()
        with langfuse.start_as_current_generation(name="result_synthesis", model=self.model) as generation:
            # Build context for synthesis
            results_text = "\n\n".join(
                f"AGENT: {r['agent']}\n"
                f"TASK: {r.get('task', 'N/A')}\n"
                f"SUCCESS: {r['success']}\n"
                f"OUTPUT:\n{r['output']}"
                for r in agent_results
            )

            system_prompt = """You are synthesizing results from multiple AI agents into a coherent response.

Your job is to:
1. Review what each agent accomplished
2. Identify any failures or issues
3. Create a clear, comprehensive response to the user's original task
4. If there were errors, explain them clearly

Be concise but thorough. Focus on answering the user's original task."""

            synthesis_context = (
                f"ORIGINAL TASK: {original_task}\n\n"
                f"EXECUTION PLAN:\n{plan.reasoning}\n\n"
                f"AGENT RESULTS:\n{results_text}\n\n"
                "Please synthesize these results into a final response."
            )

            generation.update(input={"original_task": original_task, "plan": plan.reasoning})

            logger.info(f"Synthesizing with GPT-5. Context length: {len(synthesis_context)} chars")
            logger.debug(f"Synthesis context: {synthesis_context[:1000]}")  # First 1000 chars

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": synthesis_context},
                ],
            )

            content = response.choices[0].message.content
            logger.info(f"Synthesis completed. Response length: {len(content) if content else 0} chars")
            logger.info(f"Synthesis result: {content[:500] if content else 'None'}")  # First 500 chars

            generation.update(output={"synthesis": content})
            return content or "Unable to synthesize results."

    async def orchestrate(self, task: str) -> OrchestratorResult:
        """Orchestrate execution of a complex task using multiple agents.

        Args:
            task: The user's task description

        Returns:
            OrchestratorResult with synthesis and details
        """
        langfuse = get_client()
        with langfuse.start_as_current_span(name="orchestrator_execution") as span:
            span.update(input={"task": task})

            try:
                # Step 1: Create execution plan
                logger.info(f"Creating execution plan for task: {task}")
                plan = await self._create_plan(task)
                logger.info(f"Plan created with {len(plan.tasks)} agent tasks")

                # Step 2: Execute each agent task in sequence
                agent_results: list[dict[str, Any]] = []
                for i, agent_task in enumerate(plan.tasks, 1):
                    logger.info(f"Executing task {i}/{len(plan.tasks)}: {agent_task.agent}")
                    result = await self._execute_agent_task(agent_task)
                    agent_results.append(result)

                    # Log failures but continue
                    if not result["success"]:
                        logger.warning(f"Agent {agent_task.agent} failed: {result.get('error', 'Unknown error')}")

                # Step 3: Synthesize results
                logger.info("Synthesizing results")
                synthesis = await self._synthesize_results(task, plan, agent_results)

                # Check if overall orchestration succeeded
                all_success = all(r["success"] for r in agent_results)

                span.update(
                    output={
                        "success": all_success,
                        "num_tasks": len(plan.tasks),
                        "num_successful": sum(1 for r in agent_results if r["success"]),
                    }
                )

                return OrchestratorResult(
                    success=all_success, plan=plan, agent_results=agent_results, synthesis=synthesis, error=None
                )

            except Exception as e:
                logger.error(f"Orchestration failed: {e}")
                span.update(output={"error": str(e)})
                return OrchestratorResult(
                    success=False,
                    plan=None,
                    agent_results=[],
                    synthesis=f"Orchestration failed: {str(e)}",
                    error=str(e),
                )

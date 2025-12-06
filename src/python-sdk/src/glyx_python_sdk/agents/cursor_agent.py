"""OpenAI Agent SDK wrapper for Cursor ComposableAgent."""

import logging

from agents import Agent, function_tool
from pydantic import BaseModel, Field

from glyx_python_sdk import AgentKey, ComposableAgent

logger = logging.getLogger(__name__)


class CursorTaskResult(BaseModel):
    """Result from cursor task execution."""

    success: bool = Field(..., description="Whether the task succeeded")
    output: str = Field(..., description="Task output")
    exit_code: int = Field(..., description="Process exit code")
    execution_time: float = Field(0.0, description="Execution time in seconds")


def create_run_cursor_task(github_token: str | None = None):
    """Create a run_cursor_task tool with optional GitHub token."""

    @function_tool
    async def run_cursor_task(prompt: str, model: str = "sonnet-4.5-thinking") -> str:
        """Execute a coding task using the Cursor agent.

        Use this tool to perform coding tasks like:
        - Writing new code
        - Refactoring existing code
        - Fixing bugs
        - Creating pull requests (if GitHub is connected)

        Args:
            prompt: Detailed description of the coding task
            model: Model to use for code generation

        Returns:
            Task execution result including any code changes made
        """
        logger.info(f"[CURSOR AGENT] Executing task: {prompt[:100]}...")

        agent = ComposableAgent.from_key(AgentKey.CURSOR)
        result = await agent.execute(
            {"prompt": prompt, "model": model, "force": True, "output_format": "stream-json"},
            timeout=600,
        )

        logger.info(f"[CURSOR AGENT] Completed with exit_code={result.exit_code}")
        return result.output

    return run_cursor_task


def create_cursor_agent(
    instructions: str | None = None,
    model: str = "gpt-4o",
    github_token: str | None = None,
) -> Agent:
    """Create an OpenAI Agent SDK agent wrapping the Cursor ComposableAgent.

    Tracing is handled automatically via OpenInference + Langfuse.
    Call setup_tracing() at startup to enable.

    Args:
        instructions: Custom system instructions (optional)
        model: Model for the agent's reasoning (not the cursor execution model)
        github_token: GitHub installation token for PR creation

    Returns:
        Agent instance configured with cursor tools

    Example:
        ```python
        from glyx_python_sdk.agents.cursor_agent import create_cursor_agent
        from agents import Runner

        agent = create_cursor_agent(github_token="ghs_xxx")
        result = await Runner.run(agent, input="Fix the bug in auth.py")
        ```
    """
    default_instructions = """You are a coding assistant powered by the Cursor agent.

Your capabilities:
- Write, edit, and refactor code
- Fix bugs and implement features
- Create git branches and commits
- Open pull requests (when GitHub is connected)

When given a task:
1. Analyze the requirements carefully
2. Use run_cursor_task to execute the coding work
3. Report the results clearly, including any files changed

Be precise in your prompts to run_cursor_task - include file paths, function names,
and specific requirements for best results."""

    run_cursor_task = create_run_cursor_task(github_token)

    return Agent(
        name="CursorAgent",
        instructions=instructions or default_instructions,
        model=model,
        tools=[run_cursor_task],
    )

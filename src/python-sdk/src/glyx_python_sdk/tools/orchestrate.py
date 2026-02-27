"""
A tool that orchestrates a multi-agent workflow for feature implementation,
with handoffs and hooks between agents.
"""

import asyncio
import logging

from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel

from glyx_python_sdk.settings import settings
from glyx_python_sdk.tools.filesystem import read_file, write_file, list_directory

logger = logging.getLogger(__name__)

# Use the same model setup as the main orchestrator
# Initialized at module level for performance
litellm_model = LitellmModel(
    model="openrouter/anthropic/claude-3.5-sonnet",  # Using a powerful model
    api_key=settings.openrouter_api_key,
)

# 1. Research Stage
research_agent = Agent(
    name="ResearchAgent",
    model=litellm_model,
    instructions=(
        "You are a research agent. Your task is to analyze a feature request, "
        "research the existing codebase, and create a detailed implementation plan. "
        "The plan should be clear and provide enough detail for an implementation "
        "agent to execute it. Use the provided tools to inspect the codebase."
    ),
    tools=[read_file, list_directory],
)

# 2. Implementation Stage
implementation_agent = Agent(
    name="ImplementationAgent",
    model=litellm_model,
    instructions=(
        "You are a senior software engineer. You will be given a detailed implementation "
        "plan. Your task is to implement the feature as described in the plan, writing "
        "clean, efficient, and well-documented code. Use the provided tools to read "
        "and write files."
    ),
    tools=[read_file, write_file, list_directory],
)

# 3. Review Stage Agents
code_review_agent = Agent(
    name="CodeReviewAgent",
    model=litellm_model,
    instructions=(
        "You are a code quality review agent. You will be given a summary of a new "
        "feature implementation. Your task is to review the code for quality, correctness, "
        "performance, and adherence to project standards. Use the filesystem tools to "
        "read the modified files and provide feedback."
    ),
    tools=[read_file, list_directory],
)

qa_review_agent = Agent(
    name="QAReviewAgent",
    model=litellm_model,
    instructions=(
        "You are a QA agent with a focus on product and visual quality. You will be "
        "given a summary of a newly implemented feature. Your task is to review the "
        "feature from a user's perspective, checking for usability, visual consistency, "
        "and overall user experience. Use the filesystem tools to inspect the code if "
        "needed."
    ),
    tools=[read_file, list_directory],
)


async def run_feature_implementation_workflow(prompt: str) -> str:
    """
    Runs a multi-stage workflow for implementing a new feature based on a prompt.
    """
    logger.info(f"Starting feature implementation workflow for prompt: {prompt[:100]}...")

    logger.info("Running Research Agent...")
    research_session = await Runner.run(research_agent, prompt)
    implementation_plan = research_session.final_output
    logger.info(f"Research Agent created plan:\n{implementation_plan}")

    # Hook after research
    # Here you could add validation or a manual approval step
    if not implementation_plan:
        return "Workflow failed: Research agent did not produce a plan."

    logger.info("Running Implementation Agent...")
    implementation_session = await Runner.run(implementation_agent, implementation_plan)
    # The output of this agent might be a summary of changes, not the code itself.
    # The code is written to the filesystem.
    implementation_summary = implementation_session.final_output
    logger.info(f"Implementation Agent finished with summary:\n{implementation_summary}")

    # Hook after implementation
    # Here you could run a linter or a build script

    logger.info("Running Review Agents in parallel...")
    review_prompt = (
        f"A new feature has been implemented. Here is the summary:\n{implementation_summary}\n\n"
        "Please perform your review."
    )

    code_review_session, qa_review_session = await asyncio.gather(
        Runner.run(code_review_agent, review_prompt), Runner.run(qa_review_agent, review_prompt)
    )

    code_review_feedback = code_review_session.final_output
    qa_review_feedback = qa_review_session.final_output

    logger.info(f"Code Review Feedback:\n{code_review_feedback}")
    logger.info(f"QA Review Feedback:\n{qa_review_feedback}")

    # 4. Final Summary
    final_summary = f"""
Feature implementation workflow complete.

## Implementation Plan
{implementation_plan}

## Implementation Summary
{implementation_summary}

## Code Review Feedback
{code_review_feedback}

## QA Review Feedback
{qa_review_feedback}
"""
    logger.info("Workflow finished.")
    return final_summary


# Alias for explicit import
orchestrate = run_feature_implementation_workflow

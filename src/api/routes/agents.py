"""Agent listing API routes."""

from __future__ import annotations

import json
import logging
from enum import Enum
from pathlib import Path
from typing import AsyncGenerator

from agents import ItemHelpers, Runner
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from openai.types.responses import ResponseTextDeltaEvent
from pydantic import BaseModel, Field
from supabase import create_client

from glyx_python_sdk import AgentConfig, ComposableAgent
from glyx_python_sdk.agents.glyx_sdk_agent import create_glyx_sdk_agent
from glyx_python_sdk.mcp_registry import CONTEXT7
from glyx_python_sdk.settings import settings
from glyx_python_sdk.types import AgentResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["Agents"])


class AgentVisibility(str, Enum):
    PRIVATE = "private"
    SHARED = "shared"


class CreateAgentRequest(BaseModel):
    """Request to create a new agent from config."""

    config: AgentConfig
    user_id: str | None = None
    visibility: AgentVisibility = AgentVisibility.SHARED


class CreateAgentResponse(BaseModel):
    """Response after creating an agent."""

    id: str
    agent_key: str
    visibility: AgentVisibility
    created_at: str


class CLIImportRequest(BaseModel):
    """Request to create agent from prompt, optionally with documentation URL."""

    prompt: str = Field(..., description="User prompt describing the agent to create")
    url: str | None = Field(default=None, description="Optional URL of CLI documentation")
    model: str = Field(default="gpt-4o", description="LLM model for parsing")
    org_id: str = Field(..., description="Organization/Project ID")


class CLIImportResponse(BaseModel):
    """Response from CLI import."""

    status: str = Field(description="'success' or 'needs_clarification'")
    agent_config: AgentConfig | None = Field(default=None)
    clarification_question: str | None = Field(default=None)
    source_url: str | None = Field(default=None)


def get_agents_dir() -> Path:
    """Get agents directory path from SDK."""
    import glyx_python_sdk

    sdk_path = Path(glyx_python_sdk.__file__).parent.parent
    return sdk_path / "agents"


@router.get("")
async def api_list_agents() -> list[AgentResponse]:
    """List all available agents from JSON configs."""
    agents_path = get_agents_dir()
    result: list[AgentResponse] = []

    for json_file in agents_path.glob("*.json"):
        try:
            agent = ComposableAgent.from_file(json_file)
            config = agent.config
            model_arg = config.args.get("model")
            model_default = model_arg.default if model_arg and model_arg.default else "gpt-5"
            result.append(
                AgentResponse(
                    name=config.agent_key,
                    model=str(model_default),
                    description=config.description or f"Execute {config.agent_key} agent",
                    capabilities=config.capabilities,
                    status="online",
                )
            )
        except Exception as e:
            logger.warning(f"Failed to load agent from {json_file}: {e}")
            continue

    return result


def _sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def _stream_agent_response(request: CLIImportRequest) -> AsyncGenerator[str, None]:
    """Stream agent response events as SSE."""
    logger.info(f"[AGENT_CREATE] User prompt: {request.prompt}")
    logger.info(f"[AGENT_CREATE] URL provided: {request.url}")

    async with CONTEXT7:
        agent = create_glyx_sdk_agent(model=request.model)

        if request.url:
            prompt = f"""User request: {request.prompt}

Documentation URL: {request.url}

Fetch and parse the CLI documentation from the URL above. \
Extract the CLI configuration and generate a valid AgentConfig."""
        else:
            prompt = request.prompt

        logger.info(f"[AGENT_CREATE] Final prompt: {prompt[:500]}...")

        # Use run_streamed for streaming responses
        result = Runner.run_streamed(agent, prompt)

        # Stream events as they come in
        async for event in result.stream_events():
            if event.type == "raw_response_event":
                # Stream text deltas for real-time typing effect
                if isinstance(event.data, ResponseTextDeltaEvent):
                    yield _sse_event("text_delta", {"delta": event.data.delta})

            elif event.type == "agent_updated_stream_event":
                # Agent handoff or update
                yield _sse_event(
                    "agent_update",
                    {
                        "agent_name": event.new_agent.name,
                    },
                )

            elif event.type == "run_item_stream_event":
                item = event.item

                if item.type == "tool_call_item":
                    logger.info(f"[AGENT_CREATE] tool_call_item: {item}")
                    # Tool is being called
                    tool_name = getattr(item, "name", None) or getattr(item, "tool_name", "unknown")
                    yield _sse_event(
                        "tool_call",
                        {
                            "tool_name": tool_name,
                            "status": "started",
                        },
                    )

                elif item.type == "tool_call_output_item":
                    # Tool finished with output
                    output = str(item.output)[:500] if item.output else ""
                    yield _sse_event(
                        "tool_output",
                        {
                            "output": output,
                        },
                    )

                elif item.type == "reasoning_item":
                    # Reasoning/thinking content
                    summary = getattr(item, "summary", None) or getattr(item, "text", "")
                    if summary:
                        yield _sse_event(
                            "reasoning",
                            {
                                "text": str(summary)[:1000],
                            },
                        )

                elif item.type == "message_output_item":
                    # Final message output
                    text = ItemHelpers.text_message_output(item)
                    yield _sse_event("message", {"text": text})

        # Get final output
        final_output = result.final_output
        logger.info(f"[AGENT_CREATE] result.final_output: {final_output}")

        config = result.final_output_as(AgentConfig)
        yield _sse_event(
            "complete",
            {
                "status": "success",
                "agent_config": config.model_dump(),
                "source_url": request.url or "researched",
            },
        )


@router.post("/import-stream")
async def api_import_stream(request: CLIImportRequest) -> StreamingResponse:
    """Stream agent creation with real-time events.

    Returns Server-Sent Events with:
    - text_delta: Streaming text tokens
    - tool_call: When a tool is being called
    - tool_output: Tool execution results
    - reasoning: Agent reasoning/thinking
    - agent_update: Agent handoffs
    - message: Final message outputs
    - complete: Final result with agent_config or clarification_question
    - error: Error occurred
    """
    return StreamingResponse(
        _stream_agent_response(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/import-from-url")
async def api_import_from_url(request: CLIImportRequest) -> CLIImportResponse:
    """Create agent configuration from user prompt, optionally with documentation URL."""
    try:
        logger.info(f"[AGENT_CREATE] User prompt: {request.prompt}")
        logger.info(f"[AGENT_CREATE] URL provided: {request.url}")

        async with CONTEXT7:
            agent = create_glyx_sdk_agent(model=request.model)

            if request.url:
                prompt = f"""User request: {request.prompt}

Documentation URL: {request.url}

Fetch and parse the CLI documentation from the URL above. \
Extract the CLI configuration and generate a valid AgentConfig."""
            else:
                prompt = request.prompt

            logger.info(f"[AGENT_CREATE] Final prompt: {prompt[:500]}...")

            result = await Runner.run(agent, prompt)

            logger.info(f"[AGENT_CREATE] result.final_output: {result.final_output}")

            config = result.final_output_as(AgentConfig)
            return CLIImportResponse(
                status="success",
                agent_config=config,
                source_url=request.url or "researched",
            )

    except Exception as e:
        logger.error(f"Failed to create agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def api_create_agent(request: CreateAgentRequest) -> CreateAgentResponse:
    """Create a new agent from configuration."""
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    client = create_client(settings.supabase_url, settings.supabase_anon_key)

    # Convert list-based args to dict for database storage
    args_dict = {arg.name: {k: v for k, v in arg.model_dump().items() if k != "name"} for arg in request.config.args}

    # Prepare data for workflow_templates table
    template_data = {
        "name": request.config.agent_key,
        "description": request.config.description,
        "template_key": f"custom_{request.config.agent_key}",
        "stages": [],  # Empty for single-agent configs
        "config": {
            "agent_key": request.config.agent_key,
            "command": request.config.command,
            "args": args_dict,
            "capabilities": request.config.capabilities,
            "version": request.config.version,
        },
        "user_id": request.user_id if request.visibility == AgentVisibility.PRIVATE else None,
    }

    result = client.table("workflow_templates").insert(template_data).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create agent")

    created = result.data[0]
    return CreateAgentResponse(
        id=created["id"],
        agent_key=request.config.agent_key,
        visibility=request.visibility,
        created_at=created["created_at"],
    )

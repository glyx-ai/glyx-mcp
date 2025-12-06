"""Agent listing API routes."""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

from agents import Runner
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from supabase import create_client

from glyx_python_sdk import ComposableAgent
from glyx_python_sdk.agent import AgentConfig
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
    """Request to import CLI documentation from URL."""

    url: str = Field(..., description="URL of CLI documentation")
    model: str = Field(default="gpt-5.1", description="LLM model for parsing")
    org_id: str = Field(..., description="Organization ID")


class CLIImportResponse(BaseModel):
    """Response from CLI import."""

    agent_config: AgentConfig
    source_url: str


def get_agents_dir() -> Path:
    """Get agents directory path from SDK."""
    import glyx_python_sdk
    from pathlib import Path

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


@router.post("/import-from-url")
async def api_import_from_url(request: CLIImportRequest) -> CLIImportResponse:
    """Import agent configuration from CLI documentation URL."""
    try:
        async with CONTEXT7:
            agent = create_glyx_sdk_agent(model=request.model)

            # Log agent configuration
            logger.info(f"[CLI_IMPORT] Agent name: {agent.name}")
            logger.info(f"[CLI_IMPORT] Agent model: {agent.model}")
            logger.info(f"[CLI_IMPORT] Agent output_type: {agent.output_type}")
            logger.info(f"[CLI_IMPORT] Agent handoffs: {agent.handoffs}")
            logger.info(f"[CLI_IMPORT] Agent instructions (first 500 chars): {agent.instructions[:500]}")

            prompt = f"Fetch and parse CLI documentation from {request.url}. Extract the CLI configuration."
            logger.info(f"[CLI_IMPORT] Prompt: {prompt}")

            result = await Runner.run(agent, prompt)

            # Log full result details
            logger.info(f"[CLI_IMPORT] result type: {type(result)}")
            logger.info(f"[CLI_IMPORT] result.final_output type: {type(result.final_output)}")
            logger.info(f"[CLI_IMPORT] result.final_output: {result.final_output}")
            logger.info(f"[CLI_IMPORT] result.last_agent: {result.last_agent}")

            config = result.final_output_as(AgentConfig)
            return CLIImportResponse(agent_config=config, source_url=request.url)
    except Exception as e:
        logger.error(f"Failed to import CLI from URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def api_create_agent(request: CreateAgentRequest) -> CreateAgentResponse:
    """Create a new agent from configuration."""
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    client = create_client(settings.supabase_url, settings.supabase_anon_key)

    # Prepare data for workflow_templates table
    template_data = {
        "name": request.config.agent_key,
        "description": request.config.description,
        "template_key": f"custom_{request.config.agent_key}",
        "stages": [],  # Empty for single-agent configs
        "config": {
            "agent_key": request.config.agent_key,
            "command": request.config.command,
            "args": {k: v.model_dump() for k, v in request.config.args.items()},
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

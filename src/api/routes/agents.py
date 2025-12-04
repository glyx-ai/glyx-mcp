"""Agent listing API routes."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter

from glyx_python_sdk import ComposableAgent
from glyx_python_sdk.types import AgentResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["Agents"])


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

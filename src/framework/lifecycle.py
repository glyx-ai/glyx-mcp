import logging
from enum import Enum
from typing import Optional

from integration_agents.linear_agent import LinearTools
from knockapi import Knock
from glyx_python_sdk.settings import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FeatureState(Enum):
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    VERIFICATION = "verification"
    COMPLETED = "completed"


class FeatureLifecycle:
    """Manages the lifecycle of a feature."""

    def __init__(self):
        self.linear = LinearTools()
        self._knock_client: Knock | None = None

    @property
    def knock_client(self) -> Knock:
        """Lazy-init Knock client to avoid errors when API key not set."""
        if self._knock_client is None:
            self._knock_client = Knock(api_key=settings.knock_api_key)
        return self._knock_client

    async def start_feature(self, name: str, team_id: Optional[str] = None) -> str:
        """
        Starts a new feature.
        1. Creates a Linear issue (Idea/Planning).
        2. Sends a notification.
        """
        logger.info(f"Starting feature: {name}")

        # 1. Create Linear Issue
        # We need a team ID. Ideally this comes from config or user input.
        # For now, we'll try to fetch the first team if not provided.
        if not team_id:
            teams = await self.linear.list_teams()
            if teams:
                team_id = teams[0]["id"]
            else:
                return "Error: Could not determine Linear Team ID."

        issue_result = await self.linear.create_issue(
            title=f"Feature: {name}",
            team_id=team_id,
            description=f"Tracking issue for feature: {name}",
            priority=0,  # No priority initially
        )

        logger.info(f"Linear result: {issue_result}")

        # 2. Notify
        self.knock_client.workflows.trigger(
            key="feature-lifecycle",
            recipients=["feature-channel"],
            data={"event": "started", "feature_name": name, "linear_info": issue_result},
        )
        logger.info(f"Triggered feature-lifecycle notification for {name}")

        return f"Feature '{name}' started! {issue_result}"

    async def generate_plan_template(self, name: str, output_path: str = "implementation_plan.md"):
        """Generates a standard implementation plan template."""
        content = f"""# Implementation Plan - {name}

## User Review Required
> [!IMPORTANT]
> Define critical review items here.

## Proposed Changes
### [Component Name]
#### [NEW/MODIFY] [path/to/file]
- Changes...

## Verification Plan
### Automated Tests
- ...
### Manual Verification
- ...
"""
        with open(output_path, "w") as f:
            f.write(content)

        logger.info(f"Generated plan template at {output_path}")
        return f"Plan template created at {output_path}"

from __future__ import annotations

import os
import logging
from typing import Any
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from pydantic_ai import Agent, RunContext

from api.models.linear import (
    LinearTeam,
    LinearUser,
    LinearCycle,
    LinearIssue,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearTools:
    """Tools for interacting with the Linear GraphQL API using gql."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("LINEAR_API_KEY")
        if not self.api_key:
            logger.warning("LINEAR_API_KEY not found in environment variables.")

        self._transport = AIOHTTPTransport(
            url=LINEAR_API_URL,
            headers={"Authorization": self.api_key or "", "Content-Type": "application/json"},
        )

    async def _query(self, query_str: str, variable_values: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GraphQL query against the Linear API."""
        if not self.api_key:
            raise ValueError("LINEAR_API_KEY is required to use Linear tools.")

        async with Client(transport=self._transport, fetch_schema_from_transport=False) as session:
            query = gql(query_str)
            return await session.execute(query, variable_values=variable_values)

    async def list_teams(self) -> list[LinearTeam]:
        """List all teams in the workspace."""
        query = """
        query Teams {
            teams {
                nodes {
                    id
                    name
                    key
                }
            }
        }
        """
        data = await self._query(query)
        nodes = data.get("teams", {}).get("nodes", [])
        return [LinearTeam(**node) for node in nodes]

    async def list_users(self) -> list[LinearUser]:
        """List all users in the workspace."""
        query = """
        query Users {
            users {
                nodes {
                    id
                    name
                    email
                    active
                }
            }
        }
        """
        data = await self._query(query)
        nodes = data.get("users", {}).get("nodes", [])
        return [LinearUser(**u) for u in nodes if u["active"]]

    async def list_cycles(self, team_id: str) -> list[LinearCycle]:
        """List active and upcoming cycles for a team."""
        query = """
        query Cycles($teamId: String!) {
            team(id: $teamId) {
                cycles(first: 5, filter: { endsAt: { gt: "now" } }) {
                    nodes {
                        id
                        number
                        startsAt
                        endsAt
                    }
                }
            }
        }
        """
        data = await self._query(query, {"teamId": team_id})
        team_data = data.get("team")
        if not team_data:
            return []

        nodes = team_data.get("cycles", {}).get("nodes", [])
        return [LinearCycle(**node) for node in nodes]

    async def create_issue(
        self,
        title: str,
        team_id: str,
        description: str | None = None,
        assignee_id: str | None = None,
        priority: int | None = None,
    ) -> LinearIssue:
        """Create a new issue in Linear."""
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    url
                    priority
                    state {
                        name
                        type
                    }
                    assignee {
                        name
                    }
                }
            }
        }
        """
        variables = {
            "input": {
                "title": title,
                "teamId": team_id,
                "description": description,
                "assigneeId": assignee_id,
                "priority": priority,
            }
        }
        # Remove None values
        variables["input"] = {k: v for k, v in variables["input"].items() if v is not None}

        data = await self._query(mutation, variables)
        issue_data = data.get("issueCreate", {}).get("issue", {})
        return LinearIssue(**issue_data)

    async def update_issue(
        self,
        issue_id: str,
        priority: int | None = None,
        assignee_id: str | None = None,
    ) -> LinearIssue | None:
        """Update an existing issue."""
        mutation = """
        mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    priority
                    url
                    state {
                        name
                        type
                    }
                    assignee {
                        name
                    }
                }
            }
        }
        """
        input_data = {}
        if priority is not None:
            input_data["priority"] = priority
        if assignee_id is not None:
            input_data["assigneeId"] = assignee_id

        if not input_data:
            return None

        variables = {"id": issue_id, "input": input_data}

        data = await self._query(mutation, variables)
        issue_data = data.get("issueUpdate", {}).get("issue", {})
        return LinearIssue(**issue_data)

    async def get_my_issues(self) -> list[LinearIssue]:
        """Get issues assigned to the authenticated user."""
        query = """
        query Me {
            viewer {
                assignedIssues(first: 10, filter: { state: { type: { neq: "completed" } } }) {
                    nodes {
                        id
                        identifier
                        title
                        priority
                        url
                        state {
                            name
                            type
                        }
                        assignee {
                            name
                        }
                    }
                }
            }
        }
        """
        data = await self._query(query)
        nodes = data.get("viewer", {}).get("assignedIssues", {}).get("nodes", [])
        return [LinearIssue(**node) for node in nodes]


# Define the Agent
linear_agent = Agent(
    "openai:gpt-4o",  # Or another suitable model
    system_prompt="""
    You are a Linear Integration Agent. Your goal is to help the user plan, organize, and delegate work in Linear.

    You have access to tools to:
    - List teams and users.
    - List cycles for planning.
    - Create issues.
    - Update issues (assign, prioritize).
    - View your assigned issues.

    When asked to plan work:
    1. Understand the goal.
    2. Check available teams and cycles if needed.
    3. Break down the goal into tasks and create issues.

    When asked to organize:
    1. You can prioritize issues (0=No Priority, 1=Urgent, 2=High, 3=Medium, 4=Low).

    When asked to delegate:
    1. Check available users.
    2. Assign issues to appropriate users.

    Always confirm with the user before creating or modifying a large number of items.
    For single items, you can proceed without explicit confirmation.
    """,
    deps_type=LinearTools,
)


@linear_agent.tool
async def list_teams(ctx: RunContext[LinearTools]) -> str:
    """List all teams in the Linear workspace."""
    teams = await ctx.deps.list_teams()
    return f"Found {len(teams)} teams: " + ", ".join([f"{t.name} ({t.key}) [ID: {t.id}]" for t in teams])


@linear_agent.tool
async def list_users(ctx: RunContext[LinearTools]) -> str:
    """List all active users in the Linear workspace."""
    active_users = await ctx.deps.list_users()
    return f"Found {len(active_users)} active users: " + ", ".join(
        [f"{u.name} ({u.email}) [ID: {u.id}]" for u in active_users]
    )


@linear_agent.tool
async def list_cycles(ctx: RunContext[LinearTools], team_id: str) -> str:
    """List upcoming cycles for a specific team."""
    cycles = await ctx.deps.list_cycles(team_id)
    if not cycles:
        return f"No upcoming cycles found for team {team_id} (or team not found)."
    return "Upcoming cycles for team: " + ", ".join(
        [f"Cycle {c.number} ({c.starts_at} to {c.ends_at}) [ID: {c.id}]" for c in cycles]
    )


@linear_agent.tool
async def create_issue(
    ctx: RunContext[LinearTools],
    title: str,
    team_id: str,
    description: str | None = None,
    assignee_id: str | None = None,
    priority: int | None = None,
) -> str:
    """Create a new issue in Linear."""
    issue = await ctx.deps.create_issue(title, team_id, description, assignee_id, priority)
    return f"Created issue {issue.identifier} ({issue.url})"


@linear_agent.tool
async def update_issue(
    ctx: RunContext[LinearTools], issue_id: str, priority: int | None = None, assignee_id: str | None = None
) -> str:
    """Update an existing issue's priority or assignee."""
    issue = await ctx.deps.update_issue(issue_id, priority=priority, assignee_id=assignee_id)
    if not issue:
        return "No updates made."
    return f"Updated issue {issue.identifier}"


@linear_agent.tool
async def get_my_issues(ctx: RunContext[LinearTools]) -> str:
    """Get issues assigned to the authenticated user (API key owner)."""
    issues = await ctx.deps.get_my_issues()
    if not issues:
        return "No active issues assigned to you."

    return "Your active issues:\n" + "\n".join(
        [
            f"- {i.identifier}: {i.title} (Status: {i.state.name if i.state else 'Unknown'}, Priority: {i.priority})"
            for i in issues
        ]
    )

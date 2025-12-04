"""Dynamic agent workflow composition and execution."""

from datetime import datetime
from typing import Annotated, Any
from uuid import uuid4

from pydantic import BaseModel, Field

from glyx_python_sdk.agent import AgentConfig, ArgSpec, ComposableAgent

# Type aliases
UUIDStr = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
NameStr = Annotated[str, Field(min_length=1, max_length=200)]
NonEmptyStr = Annotated[str, Field(min_length=1, max_length=10000)]


class AgentWorkflowConfig(BaseModel):
    """Dynamic agent configuration for API-driven composition."""

    id: UUIDStr = Field(default_factory=lambda: str(uuid4()))
    agent_key: NameStr
    command: NameStr
    args: dict[str, dict[str, Any]]  # Will be validated as ArgSpec when used
    description: NonEmptyStr | None = Field(default=None)
    version: str | None = Field(default=None)
    capabilities: list[str] = Field(default_factory=list)
    user_id: str | None = Field(default=None)  # NULL for global agents
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def to_agent_config(self) -> AgentConfig:
        """Convert to AgentConfig for execution."""
        args = {k: ArgSpec(**v) for k, v in self.args.items()}
        return AgentConfig(
            agent_key=self.agent_key,
            command=self.command,
            args=args,
            description=self.description,
            version=self.version,
            capabilities=self.capabilities,
        )

    def to_composable_agent(self) -> ComposableAgent:
        """Convert to ComposableAgent for execution."""
        return ComposableAgent(self.to_agent_config())


class AgentWorkflowCreate(BaseModel):
    """Request model for creating an agent workflow."""

    agent_key: NameStr
    command: NameStr
    args: dict[str, dict[str, Any]]
    description: NonEmptyStr | None = Field(default=None)
    version: str | None = Field(default=None)
    capabilities: list[str] = Field(default_factory=list)


class AgentWorkflowUpdate(BaseModel):
    """Request model for updating an agent workflow."""

    agent_key: NameStr | None = Field(default=None)
    command: NameStr | None = Field(default=None)
    args: dict[str, dict[str, Any]] | None = Field(default=None)
    description: NonEmptyStr | None = Field(default=None)
    version: str | None = Field(default=None)
    capabilities: list[str] | None = Field(default=None)


class AgentWorkflowExecuteRequest(BaseModel):
    """Request model for executing an agent workflow."""

    task_config: dict[str, Any]
    timeout: int = Field(default=120, ge=1, le=600)


# Storage functions (will use workflow_templates table in Supabase)
def get_workflow(workflow_id: UUIDStr) -> AgentWorkflowConfig | None:
    """Get an agent workflow by ID from Supabase."""
    from supabase import create_client

    from glyx_python_sdk.settings import settings

    if not settings.supabase_url or not settings.supabase_anon_key:
        raise ValueError("Supabase not configured")

    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    response = client.table("workflow_templates").select("*").eq("id", workflow_id).maybe_single().execute()

    if not response.data:
        return None

    # Map database columns to model fields
    row = response.data
    return AgentWorkflowConfig(
        id=str(row["id"]),
        agent_key=row["template_key"],  # Using template_key as agent_key
        command=row["name"],  # Using name as command for now
        args=row["config"],  # config JSONB contains args
        description=row.get("description"),
        user_id=row.get("user_id"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_workflows(user_id: str | None = None) -> list[AgentWorkflowConfig]:
    """List all agent workflows from Supabase, optionally filtered by user."""
    from supabase import create_client

    from glyx_python_sdk.settings import settings

    if not settings.supabase_url or not settings.supabase_anon_key:
        raise ValueError("Supabase not configured")

    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    query = client.table("workflow_templates").select("*").order("updated_at", desc=True)

    if user_id:
        query = query.eq("user_id", user_id)

    response = query.execute()

    return [
        AgentWorkflowConfig(
            id=str(row["id"]),
            agent_key=row["template_key"],
            command=row["name"],
            args=row["config"],
            description=row.get("description"),
            user_id=row.get("user_id"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in response.data
    ]


def save_workflow(workflow: AgentWorkflowConfig) -> AgentWorkflowConfig:
    """Save an agent workflow to Supabase (upsert)."""
    from supabase import create_client

    from glyx_python_sdk.settings import settings

    if not settings.supabase_url or not settings.supabase_anon_key:
        raise ValueError("Supabase not configured")

    workflow.updated_at = datetime.now()
    client = create_client(settings.supabase_url, settings.supabase_anon_key)

    # Map model fields to database columns
    data = {
        "id": workflow.id,
        "user_id": workflow.user_id,
        "name": workflow.command,
        "description": workflow.description,
        "template_key": workflow.agent_key,
        "stages": [],  # Not used for agent workflows
        "config": workflow.args,
        "created_at": workflow.created_at.isoformat(),
        "updated_at": workflow.updated_at.isoformat(),
    }

    response = client.table("workflow_templates").upsert(data).execute()
    return AgentWorkflowConfig(**workflow.model_dump())


def delete_workflow(workflow_id: UUIDStr) -> bool:
    """Delete an agent workflow from Supabase."""
    from supabase import create_client

    from glyx_python_sdk.settings import settings

    if not settings.supabase_url or not settings.supabase_anon_key:
        raise ValueError("Supabase not configured")

    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.table("workflow_templates").delete().eq("id", workflow_id).execute()
    return True


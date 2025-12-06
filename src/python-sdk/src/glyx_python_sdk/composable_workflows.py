"""Composable workflow models for visual workflow compositions."""

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Position(BaseModel):
    """Position coordinates for visual layout."""

    model_config = ConfigDict(strict=True)

    x: float
    y: float


class AgentInstance(BaseModel):
    """Agent instance within a workflow stage."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    id: str
    base_agent: str = Field(default="glyx", alias="baseAgent")
    system_prompt: str = Field(default="", alias="systemPrompt")
    tools: list[str] = Field(default_factory=list)

    @field_validator("system_prompt", mode="before")
    @classmethod
    def coerce_system_prompt(cls, v: str | None) -> str:
        return v or ""

    @field_validator("tools", mode="before")
    @classmethod
    def coerce_tools(cls, v: list[str] | None) -> list[str]:
        return v or []


class WorkflowStage(BaseModel):
    """A stage in the composable workflow."""

    model_config = ConfigDict(strict=True)

    id: str
    name: str
    agent: AgentInstance
    position: Position


class WorkflowConnection(BaseModel):
    """Connection between workflow stages."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    id: str
    source_stage_id: str = Field(alias="sourceStageId")
    target_stage_id: str = Field(alias="targetStageId")
    condition: str = "on_complete"


class ComposableWorkflow(BaseModel):
    """Workflow for agent generation - DB fields added separately when saving."""

    model_config = ConfigDict(strict=True)

    name: str
    description: str = ""
    stages: list[WorkflowStage] = Field(default_factory=list)
    connections: list[WorkflowConnection] = Field(default_factory=list)


# Database model with metadata fields
class ComposableWorkflowDB(BaseModel):
    """Extended model for database storage with metadata fields."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    user_id: str = Field(default="", serialization_alias="userId")
    project_id: str = Field(default="", serialization_alias="projectId")
    name: str
    description: str = ""
    template: str = ""
    stages: list[WorkflowStage] = Field(default_factory=list)
    connections: list[WorkflowConnection] = Field(default_factory=list)
    parallel_stages: list[list[str]] = Field(default_factory=list, serialization_alias="parallelStages")
    created_at: str = Field(default="", serialization_alias="createdAt")
    updated_at: str = Field(default="", serialization_alias="updatedAt")

    @field_validator("user_id", "project_id", "description", "template", "created_at", "updated_at", mode="before")
    @classmethod
    def coerce_str(cls, v: str | None) -> str:
        return v or ""

    @field_validator("stages", mode="before")
    @classmethod
    def coerce_stages(cls, v: list | None) -> list:
        return v or []

    @field_validator("connections", mode="before")
    @classmethod
    def coerce_connections(cls, v: list | None) -> list:
        return v or []

    @field_validator("parallel_stages", mode="before")
    @classmethod
    def coerce_parallel_stages(cls, v: list | None) -> list:
        return v or []


class ComposableWorkflowCreate(BaseModel):
    """Request model for creating a composable workflow."""

    name: str
    description: str = ""
    template: str = ""
    stages: list[WorkflowStage] = Field(default_factory=list)
    connections: list[WorkflowConnection] = Field(default_factory=list)
    parallel_stages: list[list[str]] = Field(default_factory=list)
    user_id: str = ""
    project_id: str = ""


class ComposableWorkflowUpdate(BaseModel):
    """Request model for updating a composable workflow."""

    name: str = ""
    description: str = ""
    template: str = ""
    stages: list[WorkflowStage] = Field(default_factory=list)
    connections: list[WorkflowConnection] = Field(default_factory=list)
    parallel_stages: list[list[str]] = Field(default_factory=list)


def _get_supabase_client():
    """Get Supabase client."""
    from supabase import create_client

    from glyx_python_sdk.settings import settings

    if not settings.supabase_url or not settings.supabase_anon_key:
        raise ValueError("Supabase not configured")

    return create_client(settings.supabase_url, settings.supabase_anon_key)


def _row_to_workflow(row: dict) -> ComposableWorkflowDB:
    """Convert database row to ComposableWorkflowDB."""
    return ComposableWorkflowDB.model_validate(row)


def get_composable_workflow(workflow_id: str) -> ComposableWorkflowDB | None:
    """Get a composable workflow by ID."""
    client = _get_supabase_client()
    response = client.table("composable_workflows").select("*").eq("id", workflow_id).maybe_single().execute()

    if not response.data:
        return None

    return _row_to_workflow(response.data)


def list_composable_workflows(
    user_id: str | None = None,
    project_id: str | None = None,
) -> list[ComposableWorkflowDB]:
    """List composable workflows, optionally filtered by user or project."""
    client = _get_supabase_client()
    query = client.table("composable_workflows").select("*").order("updated_at", desc=True)

    if user_id:
        query = query.eq("user_id", user_id)
    if project_id:
        query = query.eq("project_id", project_id)

    response = query.execute()
    return [_row_to_workflow(row) for row in response.data]


def save_composable_workflow(workflow: ComposableWorkflowDB) -> ComposableWorkflowDB:
    """Save a composable workflow (upsert)."""
    client = _get_supabase_client()
    workflow.updated_at = datetime.now().isoformat()

    data = {
        "id": workflow.id,
        "user_id": workflow.user_id or None,
        "project_id": workflow.project_id or None,
        "name": workflow.name,
        "description": workflow.description or None,
        "template": workflow.template or None,
        "stages": [s.model_dump() for s in workflow.stages],
        "connections": [c.model_dump() for c in workflow.connections],
        "parallel_stages": workflow.parallel_stages or None,
        "created_at": workflow.created_at,
        "updated_at": workflow.updated_at,
    }

    client.table("composable_workflows").upsert(data).execute()
    return workflow


def delete_composable_workflow(workflow_id: str) -> bool:
    """Delete a composable workflow."""
    client = _get_supabase_client()
    client.table("composable_workflows").delete().eq("id", workflow_id).execute()
    return True


def workflow_to_db(workflow: ComposableWorkflow) -> ComposableWorkflowDB:
    """Convert agent output to DB model with generated fields."""
    now = datetime.now().isoformat()
    return ComposableWorkflowDB(
        id=str(uuid4()),
        name=workflow.name,
        description=workflow.description,
        stages=workflow.stages,
        connections=workflow.connections,
        created_at=now,
        updated_at=now,
    )

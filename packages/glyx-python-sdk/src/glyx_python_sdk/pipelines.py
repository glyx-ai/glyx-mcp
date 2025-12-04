"""Pipeline orchestration for feature-centric workflows."""

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator
from supabase import Client, create_client

from glyx_python_sdk.agent import AgentKey, ComposableAgent
from glyx_python_sdk.settings import settings

logger = logging.getLogger(__name__)


class Role(str, Enum):
    """Agent roles in a pipeline."""

    CODER = "coder"
    REVIEWER = "reviewer"
    QA = "qa"


class StageStatus(str, Enum):
    """Status of a pipeline stage."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentSequenceStatus(str, Enum):
    """Status of an agent sequence in the pipeline."""

    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    TESTING = "testing"
    DONE = "done"


class ArtifactType(str, Enum):
    """Type of artifact produced by a stage."""

    CODE = "code"
    REVIEW = "review"
    TEST = "test"


class ActorType(str, Enum):
    """Type of actor in a conversation."""

    USER = "user"
    AGENT = "agent"


UUIDStr = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
NonEmptyStr = Annotated[str, Field(min_length=1, max_length=10000)]
NameStr = Annotated[str, Field(min_length=1, max_length=200)]


class AgentInstance(BaseModel):
    """Configuration for an agent assigned to a role."""

    id: UUIDStr = Field(default_factory=lambda: str(uuid4()))
    base_agent: AgentKey
    role: Role


class Stage(BaseModel):
    """A single stage in the pipeline."""

    id: UUIDStr = Field(default_factory=lambda: str(uuid4()))
    name: NameStr
    role: Role
    agent: AgentInstance | None = None
    status: StageStatus = Field(default=StageStatus.PENDING)
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    error: NonEmptyStr | None = Field(default=None)

    @computed_field
    @property
    def duration(self) -> timedelta | None:
        """Compute stage execution duration."""
        return (self.completed_at - self.started_at) if (self.started_at and self.completed_at) else None

    @computed_field
    @property
    def is_terminal(self) -> bool:
        """Check if stage is in terminal state."""
        return self.status in {StageStatus.COMPLETED, StageStatus.FAILED}

    @model_validator(mode="after")
    def validate_timestamps(self) -> "Stage":
        """Validate timestamp ordering."""
        if self.started_at and self.completed_at and self.completed_at < self.started_at:
            raise ValueError("completed_at must be after started_at")
        return self


class Artifact(BaseModel):
    """Output artifact from a stage."""

    id: UUIDStr = Field(default_factory=lambda: str(uuid4()))
    type: ArtifactType
    content: NonEmptyStr
    stage_id: UUIDStr
    created_at: datetime = Field(default_factory=datetime.now)


class ConversationEvent(BaseModel):
    """A single event in the agent sequence conversation."""

    id: UUIDStr = Field(default_factory=lambda: str(uuid4()))
    agent_sequence_id: UUIDStr
    actor_type: ActorType
    role: Role | None = Field(default=None)
    stage_id: UUIDStr | None = Field(default=None)
    content: NonEmptyStr
    timestamp: datetime = Field(default_factory=datetime.now)


class AgentSequence(BaseModel):
    """A sequence of agent stages being executed through the pipeline."""

    id: UUIDStr = Field(default_factory=lambda: str(uuid4()))
    name: NameStr
    description: NonEmptyStr
    status: AgentSequenceStatus = Field(default=AgentSequenceStatus.IN_PROGRESS)
    stages: list[Stage] = Field(default_factory=list, min_length=1)
    artifacts: list[Artifact] = Field(default_factory=list)
    events: list[ConversationEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @computed_field
    @property
    def current_stage(self) -> Stage | None:
        """Get the currently running stage."""
        return next((s for s in self.stages if s.status == StageStatus.RUNNING), None)

    @computed_field
    @property
    def progress(self) -> float:
        """Compute pipeline completion progress (0.0 to 1.0)."""
        return len([s for s in self.stages if s.is_terminal]) / len(self.stages) if self.stages else 0.0

    @computed_field
    @property
    def total_duration(self) -> timedelta:
        """Compute total execution time across all completed stages."""
        return sum((s.duration for s in self.stages if s.duration), timedelta())

    @field_validator("stages")
    @classmethod
    def validate_unique_stage_ids(cls, stages: list[Stage]) -> list[Stage]:
        """Ensure all stage IDs are unique."""
        stage_ids = [s.id for s in stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError("Stage IDs must be unique")
        return stages

    @model_validator(mode="after")
    def validate_artifact_references(self) -> "AgentSequence":
        """Validate artifact stage_id references exist."""
        stage_ids = {s.id for s in self.stages}
        invalid_artifacts = [a for a in self.artifacts if a.stage_id not in stage_ids]
        if invalid_artifacts:
            raise ValueError(f"Artifacts reference non-existent stages: {[a.id for a in invalid_artifacts]}")
        return self

    @model_validator(mode="after")
    def validate_event_references(self) -> "AgentSequence":
        """Validate event references exist."""
        stage_ids = {s.id for s in self.stages}
        invalid_events = [e for e in self.events if e.stage_id and e.stage_id not in stage_ids]
        if invalid_events:
            raise ValueError(f"Events reference non-existent stages: {[e.id for e in invalid_events]}")
        return self

    def add_event(self, content: NonEmptyStr, actor_type: ActorType, **kwargs: NonEmptyStr | Role | None) -> ConversationEvent:
        """Add a conversation event."""
        event = ConversationEvent(agent_sequence_id=self.id, actor_type=actor_type, content=content, **kwargs)
        self.events.append(event)
        self.updated_at = datetime.now()
        return event


class AgentSequenceCreate(BaseModel):
    """Request model for creating an agent sequence."""

    name: NameStr
    description: NonEmptyStr


class AgentSequenceUpdate(BaseModel):
    """Request model for updating an agent sequence."""

    name: NameStr | None = Field(default=None)
    description: NonEmptyStr | None = Field(default=None)
    status: AgentSequenceStatus | None = Field(default=None)


def create_default_stages() -> list[Stage]:
    """Create default pipeline: Coder -> Reviewer -> QA."""
    return [
        Stage(name="Implementation", role=Role.CODER, agent=AgentInstance(base_agent=AgentKey.CURSOR, role=Role.CODER)),
        Stage(
            name="Code Review", role=Role.REVIEWER, agent=AgentInstance(base_agent=AgentKey.CLAUDE, role=Role.REVIEWER)
        ),
        Stage(name="Testing", role=Role.QA, agent=AgentInstance(base_agent=AgentKey.CLAUDE, role=Role.QA)),
    ]


class Pipeline:
    """Orchestrates agent sequence workflow through stages."""

    def __init__(self, agent_sequence: AgentSequence):
        self.agent_sequence = agent_sequence

    @classmethod
    def create(cls, create_req: AgentSequenceCreate) -> "Pipeline":
        """Create a new pipeline from an agent sequence creation request."""
        agent_sequence = AgentSequence(
            name=create_req.name,
            description=create_req.description,
            stages=create_default_stages(),
        )
        return cls(agent_sequence)

    async def run_stage(self, stage_id: UUIDStr, prompt: NonEmptyStr) -> Artifact | None:
        """Execute a specific stage with the given prompt."""
        stage = next((s for s in self.agent_sequence.stages if s.id == stage_id), None)
        if not stage or not stage.agent:
            logger.error(f"Stage {stage_id} not found or has no agent")
            return None

        stage.status = StageStatus.RUNNING
        stage.started_at = datetime.now()
        self.agent_sequence.updated_at = datetime.now()
        self.agent_sequence.add_event(content=prompt, actor_type=ActorType.USER, stage_id=stage_id)

        try:
            agent = ComposableAgent.from_key(stage.agent.base_agent)
            result = await agent.execute({"prompt": prompt, "model": "gpt-5"}, timeout=300)

            stage.status = StageStatus.COMPLETED if result.success else StageStatus.FAILED
            stage.completed_at = datetime.now()
            stage.error = result.stderr if not result.success else None

            artifact_type_map = {Role.CODER: ArtifactType.CODE, Role.REVIEWER: ArtifactType.REVIEW, Role.QA: ArtifactType.TEST}
            artifact_type = artifact_type_map[stage.role]
            artifact = Artifact(type=artifact_type, content=result.stdout, stage_id=stage_id)
            self.agent_sequence.artifacts.append(artifact)
            self.agent_sequence.add_event(content=result.stdout, actor_type=ActorType.AGENT, role=stage.role, stage_id=stage_id)

            return artifact

        except Exception as e:
            logger.exception(f"Stage {stage_id} failed")
            stage.status = StageStatus.FAILED
            stage.completed_at = datetime.now()
            stage.error = str(e)
            return None

    def get_next_stage(self) -> Stage | None:
        """Get the next pending stage."""
        return next((s for s in self.agent_sequence.stages if s.status == StageStatus.PENDING), None)


def get_supabase_client() -> Client:
    """Get Supabase client for pipelines."""
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise ValueError("Supabase not configured")
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def get_agent_sequence(sequence_id: UUIDStr) -> AgentSequence | None:
    """Get an agent sequence by ID from Supabase."""
    client = get_supabase_client()
    response = client.table("agent_sequences").select("*").eq("id", sequence_id).maybe_single().execute()
    return AgentSequence(**response.data) if response.data else None


def list_agent_sequences(status: AgentSequenceStatus | None = None) -> list[AgentSequence]:
    """List all agent sequences from Supabase, optionally filtered by status."""
    client = get_supabase_client()
    query = client.table("agent_sequences").select("*").order("updated_at", desc=True)
    query = query.eq("status", status) if status else query
    response = query.execute()
    return [AgentSequence(**row) for row in response.data]


def save_agent_sequence(agent_sequence: AgentSequence) -> AgentSequence:
    """Save an agent sequence to Supabase (upsert)."""
    agent_sequence.updated_at = datetime.now()
    client = get_supabase_client()
    data = agent_sequence.model_dump(mode="json")
    response = client.table("agent_sequences").upsert(data).execute()
    return AgentSequence(**response.data[0])


def delete_agent_sequence(sequence_id: UUIDStr) -> bool:
    """Delete an agent sequence from Supabase."""
    client = get_supabase_client()
    client.table("agent_sequences").delete().eq("id", sequence_id).execute()
    return True


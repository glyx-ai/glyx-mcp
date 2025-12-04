"""Pipeline orchestration for feature-centric workflows."""

import logging
from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from glyx_sdk.agent import AgentKey, ComposableAgent

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


class AgentInstance(BaseModel):
    """Configuration for an agent assigned to a role."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    base_agent: AgentKey
    role: Role


class Stage(BaseModel):
    """A single stage in the pipeline."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    role: Role
    agent: AgentInstance | None = None
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class Artifact(BaseModel):
    """Output artifact from a stage."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: Literal["code", "review", "test"]
    content: str
    stage_id: str
    created_at: datetime = Field(default_factory=datetime.now)


class ConversationEvent(BaseModel):
    """A single event in the feature conversation."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    feature_id: str
    actor_type: Literal["user", "agent"]
    role: Role | None = None
    stage_id: str | None = None
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class Feature(BaseModel):
    """A feature being developed through the pipeline."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: str
    status: Literal["in_progress", "review", "testing", "done"] = "in_progress"
    stages: list[Stage] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    events: list[ConversationEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def current_stage(self) -> Stage | None:
        """Get the currently running stage."""
        return next((s for s in self.stages if s.status == StageStatus.RUNNING), None)

    def add_event(self, content: str, actor_type: Literal["user", "agent"], **kwargs) -> ConversationEvent:
        """Add a conversation event."""
        event = ConversationEvent(feature_id=self.id, actor_type=actor_type, content=content, **kwargs)
        self.events.append(event)
        self.updated_at = datetime.now()
        return event


class FeatureCreate(BaseModel):
    """Request model for creating a feature."""

    name: str
    description: str


class FeatureUpdate(BaseModel):
    """Request model for updating a feature."""

    name: str | None = None
    description: str | None = None
    status: Literal["in_progress", "review", "testing", "done"] | None = None


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
    """Orchestrates feature workflow through stages."""

    def __init__(self, feature: Feature):
        self.feature = feature

    @classmethod
    def create(cls, create_req: FeatureCreate) -> "Pipeline":
        """Create a new pipeline from a feature creation request."""
        feature = Feature(
            name=create_req.name,
            description=create_req.description,
            stages=create_default_stages(),
        )
        return cls(feature)

    async def run_stage(self, stage_id: str, prompt: str) -> Artifact | None:
        """Execute a specific stage with the given prompt."""
        stage = next((s for s in self.feature.stages if s.id == stage_id), None)
        if not stage or not stage.agent:
            logger.error(f"Stage {stage_id} not found or has no agent")
            return None

        stage.status = StageStatus.RUNNING
        stage.started_at = datetime.now()
        self.feature.updated_at = datetime.now()
        self.feature.add_event(content=prompt, actor_type="user", stage_id=stage_id)

        try:
            agent = ComposableAgent.from_key(stage.agent.base_agent)
            result = await agent.execute({"prompt": prompt, "model": "gpt-5"}, timeout=300)

            stage.status = StageStatus.COMPLETED if result.success else StageStatus.FAILED
            stage.completed_at = datetime.now()
            stage.error = result.stderr if not result.success else None

            artifact_type: Literal["code", "review", "test"] = (
                "code" if stage.role == Role.CODER else "review" if stage.role == Role.REVIEWER else "test"
            )
            artifact = Artifact(type=artifact_type, content=result.stdout, stage_id=stage_id)
            self.feature.artifacts.append(artifact)
            self.feature.add_event(content=result.stdout, actor_type="agent", role=stage.role, stage_id=stage_id)

            return artifact

        except Exception as e:
            logger.exception(f"Stage {stage_id} failed")
            stage.status = StageStatus.FAILED
            stage.completed_at = datetime.now()
            stage.error = str(e)
            return None

    def get_next_stage(self) -> Stage | None:
        """Get the next pending stage."""
        return next((s for s in self.feature.stages if s.status == StageStatus.PENDING), None)


# In-memory store for MVP (will be replaced with DB)
_features_store: dict[str, Feature] = {}


def get_feature(feature_id: str) -> Feature | None:
    """Get a feature by ID."""
    return _features_store.get(feature_id)


def list_features(status: str | None = None) -> list[Feature]:
    """List all features, optionally filtered by status."""
    features = list(_features_store.values())
    return [f for f in features if f.status == status] if status else features


def save_feature(feature: Feature) -> Feature:
    """Save a feature to the store."""
    _features_store[feature.id] = feature
    return feature


def delete_feature(feature_id: str) -> bool:
    """Delete a feature from the store."""
    if feature_id in _features_store:
        del _features_store[feature_id]
        return True
    return False


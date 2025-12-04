"""Pydantic models for SDK API."""

import re

from pydantic import BaseModel, Field, computed_field


class TaskData(BaseModel):
    """Task data for agent execution."""

    id: str
    title: str
    description: str | None = None
    agents: list[str] = Field(default_factory=list)


class StreamCursorRequest(BaseModel):
    """Request model for streaming cursor agent."""

    task: TaskData
    organization_id: str
    organization_name: str | None = None


class AgentResponse(BaseModel):
    """Response model for agent info."""

    name: str
    model: str
    description: str
    capabilities: list[str]
    status: str


class OrganizationCreate(BaseModel):
    """Request model for creating an organization."""

    name: str
    description: str = ""
    template: str = ""
    config: dict = Field(default_factory=dict)


class OrganizationResponse(BaseModel):
    """Response model for organization."""

    id: str
    name: str
    description: str
    status: str
    template: str
    config: dict
    stages: list
    created_at: str

    @computed_field
    @property
    def slug(self) -> str:
        """URL-safe slug derived from name."""
        return re.sub(r"[^a-z0-9-]", "", re.sub(r"\s+", "-", self.name.lower()))


class SaveMemoryRequest(BaseModel):
    """Request model for saving memory."""

    content: str
    category: str
    agent_id: str = "dashboard"
    run_id: str | None = None
    directory_name: str = "glyx"


class SearchMemoryRequest(BaseModel):
    """Request model for searching memory."""

    query: str
    category: str | None = None
    limit: int = 10


class AuthSignUpRequest(BaseModel):
    """Request model for sign up."""

    email: str
    password: str
    metadata: dict = Field(default_factory=dict)


class AuthSignInRequest(BaseModel):
    """Request model for sign in."""

    email: str
    password: str


class AuthResponse(BaseModel):
    """Response model for auth operations."""

    user_id: str | None = None
    email: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: int | None = None


class SmartTaskRequest(BaseModel):
    """Request model for AI-powered smart task creation."""

    selected_text: str
    page_url: str | None = None
    page_title: str | None = None


class TaskResponse(BaseModel):
    """Response model for task."""

    id: str
    title: str
    description: str
    status: str
    organization_id: str | None = None
    created_at: str


class MemoryInferRequest(BaseModel):
    """Request model for AI-powered memory inference."""

    page_content: str
    page_url: str | None = None
    page_title: str | None = None
    user_context: str | None = None


class MemorySuggestion(BaseModel):
    """A suggested memory to save."""

    content: str
    category: str
    reason: str


class MemoryInferResponse(BaseModel):
    """Response model for memory inference."""

    suggestions: list[MemorySuggestion]
    analysis: str


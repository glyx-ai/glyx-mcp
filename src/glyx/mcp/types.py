"""Pydantic models for FastMCP API."""

from pydantic import BaseModel, Field


class StreamCursorRequest(BaseModel):
    """Request model for streaming cursor agent."""
    prompt: str
    model: str = "gpt-5"
    conversation_id: str | None = None
    task_id: str | None = None
    organization_id: str | None = None
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

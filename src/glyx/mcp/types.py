"""Pydantic models for FastMCP API."""

from pydantic import BaseModel, Field


class StreamCursorRequest(BaseModel):
    """Request model for streaming cursor agent."""
    prompt: str
    model: str = "gpt-5"
    conversation_id: str | None = None


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

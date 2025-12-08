from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class LinearTeam(BaseModel):
    """Linear Team model."""

    id: str
    name: str
    key: str


class LinearUser(BaseModel):
    """Linear User model."""

    id: str
    name: str
    email: str
    active: bool


class LinearCycle(BaseModel):
    """Linear Cycle model."""

    id: str
    number: int
    starts_at: str = Field(alias="startsAt")
    ends_at: str = Field(alias="endsAt")


class LinearState(BaseModel):
    """Linear Issue State model."""

    name: str
    type: str | None = None


class LinearAssignee(BaseModel):
    """Linear Issue Assignee model."""

    name: str


class LinearIssue(BaseModel):
    """Linear Issue model."""

    id: str
    identifier: str
    title: str
    priority: int
    state: Optional[LinearState] = None
    assignee: Optional[LinearAssignee] = None
    url: Optional[str] = None

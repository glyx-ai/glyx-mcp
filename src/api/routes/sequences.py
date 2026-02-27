"""Agent sequences API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from glyx_python_sdk import (
    AgentSequence,
    AgentSequenceCreate,
    AgentSequenceUpdate,
    Pipeline,
    delete_agent_sequence,
    get_agent_sequence,
    list_agent_sequences,
    save_agent_sequence,
)

router = APIRouter(prefix="/api/agent-sequences", tags=["Agent Sequences"])


@router.get("", summary="List Agent Sequences", response_description="List of agent sequences")
async def api_list_agent_sequences(status: str | None = None) -> list[AgentSequence]:
    """
    List all agent sequences, optionally filtered by status.

    **Query Parameters:**
    - `status` (optional): Filter by status ("in_progress", "review", "testing", "done")

    **Returns:** Array of AgentSequence objects with stages, artifacts, and conversation history
    """
    return list_agent_sequences(status)


@router.post(
    "",
    summary="Create Agent Sequence",
    response_description="Created agent sequence with default pipeline",
    status_code=201,
)
async def api_create_agent_sequence(body: AgentSequenceCreate) -> AgentSequence:
    """
    Create a new agent sequence with default 3-stage pipeline.

    Creates an agent sequence with:
    1. **Implementation** stage (CODER role with CURSOR agent)
    2. **Code Review** stage (REVIEWER role with CLAUDE agent)
    3. **Testing** stage (QA role with CLAUDE agent)

    **Request Body:**
    - `name`: Sequence name
    - `description`: Sequence description

    **Example:**
    ```json
    {
        "name": "User Authentication",
        "description": "JWT-based authentication with refresh tokens"
    }
    ```
    """
    pipeline = Pipeline.create(body)
    return save_agent_sequence(pipeline.agent_sequence)


@router.get("/{sequence_id}")
async def api_get_agent_sequence(sequence_id: str) -> AgentSequence:
    """Get an agent sequence by ID."""
    agent_sequence = get_agent_sequence(sequence_id)
    if not agent_sequence:
        raise HTTPException(status_code=404, detail="Agent sequence not found")
    return agent_sequence


@router.patch("/{sequence_id}")
async def api_update_agent_sequence(sequence_id: str, body: AgentSequenceUpdate) -> AgentSequence:
    """Update an agent sequence."""
    agent_sequence = get_agent_sequence(sequence_id)
    if not agent_sequence:
        raise HTTPException(status_code=404, detail="Agent sequence not found")
    updated = agent_sequence.model_copy(update=body.model_dump(exclude_unset=True))
    return save_agent_sequence(updated)


@router.delete("/{sequence_id}")
async def api_delete_agent_sequence(sequence_id: str) -> dict[str, str]:
    """Delete an agent sequence."""
    if not delete_agent_sequence(sequence_id):
        raise HTTPException(status_code=404, detail="Agent sequence not found")
    return {"status": "deleted"}

"""Agent workflows API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from glyx_python_sdk.workflows import (
    AgentWorkflowConfig,
    AgentWorkflowCreate,
    AgentWorkflowExecuteRequest,
    AgentWorkflowUpdate,
    delete_workflow,
    get_workflow,
    list_workflows,
    save_workflow,
)

router = APIRouter(prefix="/api/agent-workflows", tags=["Agent Workflows"])


@router.get("", summary="List Agent Workflows")
async def api_list_workflows(user_id: str | None = None) -> list[AgentWorkflowConfig]:
    """
    List all agent workflows, optionally filtered by user.

    **Query Parameters:**
    - `user_id` (optional): Filter by user ID (omit for global workflows)

    **Returns:** Array of AgentWorkflowConfig objects matching agents/*.json structure
    """
    return list_workflows(user_id)


@router.post("", summary="Create Agent Workflow", status_code=201)
async def api_create_workflow(body: AgentWorkflowCreate) -> AgentWorkflowConfig:
    """
    Create a new agent workflow with JSON config structure.

    Creates a custom agent similar to agents/*.json files but stored in database.

    **Request Body:**
    - `agent_key`: Unique identifier for this agent
    - `command`: CLI command to execute
    - `args`: Dict of argument specifications (flag, type, required, default, description)
    - `description` (optional): Human-readable description
    - `version` (optional): Version string
    - `capabilities` (optional): List of capability tags

    **Example:**
    ```json
    {
        "agent_key": "my_custom_agent",
        "command": "python",
        "args": {
            "script": {
                "flag": "",
                "type": "string",
                "required": true,
                "description": "Python script to run"
            },
            "verbose": {
                "flag": "--verbose",
                "type": "bool",
                "required": false,
                "default": false
            }
        },
        "description": "Custom Python script executor"
    }
    ```
    """
    workflow = AgentWorkflowConfig(**body.model_dump())
    return save_workflow(workflow)


@router.get("/{workflow_id}")
async def api_get_workflow(workflow_id: str) -> AgentWorkflowConfig:
    """Get an agent workflow by ID."""
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.patch("/{workflow_id}")
async def api_update_workflow(workflow_id: str, body: AgentWorkflowUpdate) -> AgentWorkflowConfig:
    """Update an agent workflow."""
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    updated = workflow.model_copy(update=body.model_dump(exclude_unset=True))
    return save_workflow(updated)


@router.delete("/{workflow_id}")
async def api_delete_workflow(workflow_id: str) -> dict[str, str]:
    """Delete an agent workflow."""
    if not delete_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"status": "deleted"}


@router.post("/{workflow_id}/execute")
async def api_execute_workflow(workflow_id: str, body: AgentWorkflowExecuteRequest) -> dict[str, Any]:
    """
    Execute a custom agent workflow.

    **Path Parameters:**
    - `workflow_id`: ID of the workflow to execute

    **Request Body:**
    - `task_config`: Task configuration (e.g., {"prompt": "...", "files": "..."})
    - `timeout` (optional): Execution timeout in seconds (default: 120, max: 600)

    **Returns:** Agent execution result with stdout, stderr, exit_code, success
    """
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    agent = workflow.to_composable_agent()
    result = await agent.execute(body.task_config, timeout=body.timeout)

    return {
        "success": result.success,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "execution_time": result.execution_time,
        "timed_out": result.timed_out,
    }

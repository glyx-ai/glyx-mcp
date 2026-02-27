"""Composable workflows API routes for visual workflow compositions."""

from agents import Runner
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from glyx_python_sdk.agents.workflow_agent import create_workflow_agent
from glyx_python_sdk.composable_workflows import (
    ComposableWorkflowCreate,
    ComposableWorkflowDB,
    ComposableWorkflowUpdate,
    delete_composable_workflow,
    get_composable_workflow,
    list_composable_workflows,
    save_composable_workflow,
    workflow_to_db,
)

router = APIRouter(prefix="/api/composable-workflows", tags=["Composable Workflows"])


class WorkflowGenerateRequest(BaseModel):
    """Request body for workflow generation."""

    prompt: str
    model: str = "gpt-5.1"


@router.post("/generate", summary="Generate Workflow with AI")
async def api_generate_workflow(body: WorkflowGenerateRequest) -> JSONResponse:
    """Generate a composable workflow from a natural language description.

    Uses an AI agent to create a workflow configuration based on the user's prompt.
    """
    agent = create_workflow_agent(model=body.model)
    result = await Runner.run(agent, body.prompt)
    workflow = workflow_to_db(result.final_output)
    return JSONResponse(content=workflow.model_dump(by_alias=True))


@router.get("", summary="List Composable Workflows")
async def api_list_workflows(
    user_id: str | None = None,
    project_id: str | None = None,
) -> JSONResponse:
    """List all composable workflows, optionally filtered by user or project."""
    workflows = list_composable_workflows(user_id=user_id, project_id=project_id)
    return JSONResponse(content=[w.model_dump(by_alias=True) for w in workflows])


@router.post("", summary="Create Composable Workflow", status_code=201)
async def api_create_workflow(body: ComposableWorkflowCreate) -> JSONResponse:
    """Create a new composable workflow with visual stage/connection configuration."""
    from datetime import datetime
    from uuid import uuid4

    workflow = ComposableWorkflowDB(
        id=str(uuid4()),
        user_id=body.user_id,
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        template=body.template,
        stages=body.stages,
        connections=body.connections,
        parallel_stages=body.parallel_stages,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )
    saved = save_composable_workflow(workflow)
    return JSONResponse(content=saved.model_dump(by_alias=True), status_code=201)


@router.get("/{workflow_id}", summary="Get Composable Workflow")
async def api_get_workflow(workflow_id: str) -> JSONResponse:
    """Get a composable workflow by ID."""
    workflow = get_composable_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return JSONResponse(content=workflow.model_dump(by_alias=True))


@router.patch("/{workflow_id}", summary="Update Composable Workflow")
async def api_update_workflow(workflow_id: str, body: ComposableWorkflowUpdate) -> JSONResponse:
    """Update a composable workflow."""
    workflow = get_composable_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    updated = workflow.model_copy(update=body.model_dump(exclude_unset=True))
    saved = save_composable_workflow(updated)
    return JSONResponse(content=saved.model_dump(by_alias=True))


@router.delete("/{workflow_id}", summary="Delete Composable Workflow")
async def api_delete_workflow(workflow_id: str) -> dict[str, str]:
    """Delete a composable workflow."""
    workflow = get_composable_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    delete_composable_workflow(workflow_id)
    return {"status": "deleted"}

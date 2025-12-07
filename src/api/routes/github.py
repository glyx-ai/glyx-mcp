"""GitHub API routes scoped to projects."""

from __future__ import annotations

import logging
from typing import Union

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel
from supabase import create_client

from glyx_python_sdk.integrations.github import FileContent, GitHubClient
from glyx_python_sdk.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/github", tags=["GitHub"])

_client: GitHubClient | None = None


def get_client() -> GitHubClient:
    """Get or create GitHub client singleton."""
    global _client
    if _client is None:
        _client = GitHubClient()
    return _client


def _get_supabase():
    return create_client(settings.supabase_url, settings.supabase_anon_key)


class GitHubInstallationResponse(BaseModel):
    """GitHub installation response model."""

    id: str
    installation_id: int
    account_type: str
    account_login: str
    account_id: int
    target_type: str
    permissions: dict
    events: list
    suspended_at: str | None = None
    created_at: str
    updated_at: str


class GitHubRepositoryResponse(BaseModel):
    """GitHub repository response model."""

    id: str
    installation_id: str
    github_id: int
    owner: str
    name: str
    full_name: str
    description: str | None = None
    is_private: bool = False
    default_branch: str = "main"
    html_url: str | None = None
    synced_at: str
    created_at: str


@router.get("/installations", response_model=list[GitHubInstallationResponse])
async def list_project_installations(
    project_id: str = Path(..., description="Project ID"),
) -> list[GitHubInstallationResponse]:
    """List GitHub App installations for a project."""
    client = _get_supabase()
    response = client.table("github_installations").select("*").eq("project_id", project_id).execute()
    return [GitHubInstallationResponse(**row) for row in response.data]


@router.get("/repositories", response_model=list[GitHubRepositoryResponse])
async def list_project_repositories(
    project_id: str = Path(..., description="Project ID"),
) -> list[GitHubRepositoryResponse]:
    """List all repositories for a project's GitHub installations."""
    client = _get_supabase()
    installations = client.table("github_installations").select("id").eq("project_id", project_id).execute()
    installation_ids = [row["id"] for row in installations.data]

    if not installation_ids:
        return []

    repos = client.table("github_repositories").select("*").in_("installation_id", installation_ids).execute()
    return [GitHubRepositoryResponse(**row) for row in repos.data]


@router.get(
    "/repositories/{owner}/{repo}/contents/{path:path}",
    response_model=Union[FileContent, list[FileContent]],
)
async def get_contents(
    project_id: str = Path(..., description="Project ID"),
    owner: str = Path(..., description="Repository owner"),
    repo: str = Path(..., description="Repository name"),
    path: str = Path(..., description="File or directory path"),
    ref: str | None = Query(default=None, description="Git ref (branch, tag, or commit SHA)"),
) -> FileContent | list[FileContent]:
    """Get file or directory contents from a repository."""
    installation_id = await _get_installation_id_for_repo(project_id, owner, repo)
    client = get_client()
    return await client.get_contents(installation_id, owner, repo, path, ref)


@router.get("/repositories/{owner}/{repo}/tree", response_model=dict)
async def get_tree(
    project_id: str = Path(..., description="Project ID"),
    owner: str = Path(..., description="Repository owner"),
    repo: str = Path(..., description="Repository name"),
    tree_sha: str = Query(default="HEAD", description="Tree SHA or ref"),
    recursive: bool = Query(default=True, description="Include subdirectories"),
) -> dict:
    """Get repository file tree."""
    installation_id = await _get_installation_id_for_repo(project_id, owner, repo)
    client = get_client()
    return await client.get_tree(installation_id, owner, repo, tree_sha, recursive)


async def _get_installation_id_for_repo(project_id: str, owner: str, repo: str) -> int:
    """Get GitHub installation ID for a repository within a project."""
    client = _get_supabase()
    full_name = f"{owner}/{repo}"

    result = (
        client.table("github_repositories")
        .select("github_installations!inner(installation_id, project_id)")
        .eq("full_name", full_name)
        .eq("github_installations.project_id", project_id)
        .maybe_single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail=f"Repository {full_name} not found in project")

    return result.data["github_installations"]["installation_id"]

"""GitHub API routes for repository content retrieval."""

from __future__ import annotations

import logging
from typing import Union

from fastapi import APIRouter, HTTPException, Query

from glyx_python_sdk.integrations.github import FileContent, GitHubClient, GitHubInstallation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/github", tags=["GitHub"])

_client: GitHubClient | None = None


def get_client() -> GitHubClient:
    """Get or create GitHub client singleton."""
    global _client
    if _client is None:
        _client = GitHubClient()
    return _client


@router.get("/installations", response_model=list[GitHubInstallation])
async def list_installations() -> list[GitHubInstallation]:
    """List all GitHub App installations."""
    try:
        client = get_client()
        return await client.list_installations()
    except Exception as e:
        logger.exception(f"Failed to list installations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/installations/{installation_id}/repos/{owner}/{repo}/contents/{path:path}",
    response_model=Union[FileContent, list[FileContent]],
)
async def get_contents(
    installation_id: int,
    owner: str,
    repo: str,
    path: str,
    ref: str | None = Query(default=None, description="Git ref (branch, tag, or commit SHA)"),
) -> FileContent | list[FileContent]:
    """Get file or directory contents from a repository.

    Returns FileContent for files (with base64-encoded content) or
    list[FileContent] for directories.
    """
    try:
        client = get_client()
        return await client.get_contents(installation_id, owner, repo, path, ref)
    except Exception as e:
        logger.exception(f"Failed to get contents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/installations/{installation_id}/repos/{owner}/{repo}/tree",
    response_model=dict,
)
async def get_tree(
    installation_id: int,
    owner: str,
    repo: str,
    tree_sha: str = Query(default="HEAD", description="Tree SHA or ref"),
    recursive: bool = Query(default=True, description="Include subdirectories"),
) -> dict:
    """Get repository file tree."""
    try:
        client = get_client()
        return await client.get_tree(installation_id, owner, repo, tree_sha, recursive)
    except Exception as e:
        logger.exception(f"Failed to get tree: {e}")
        raise HTTPException(status_code=500, detail=str(e))

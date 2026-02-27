"""GitHub App integration for file content retrieval."""

from __future__ import annotations

import base64
import logging
import time
from pathlib import Path
from typing import Any, Literal

import httpx
import jwt
from pydantic import BaseModel, Field

from glyx_python_sdk.settings import settings

logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com"


def _load_private_key(key_or_path: str | None) -> str | None:
    """Load private key from string or file path."""
    if not key_or_path:
        return None

    # If it looks like a PEM key, return as-is
    if "-----BEGIN" in key_or_path:
        return key_or_path

    # Try to load from file path
    path = Path(key_or_path).expanduser()
    if path.exists():
        return path.read_text()

    # Return as-is (might be the key content without markers)
    return key_or_path


class FileContent(BaseModel):
    """GitHub file or directory content."""

    name: str
    path: str
    sha: str
    size: int
    type: Literal["file", "dir", "symlink", "submodule"]
    content: str | None = None
    encoding: str | None = None
    download_url: str | None = None
    url: str
    html_url: str | None = None
    git_url: str | None = None

    def decode_content(self) -> str:
        """Decode base64 content to string."""
        if not self.content or self.encoding != "base64":
            return self.content or ""
        return base64.b64decode(self.content).decode("utf-8")


class GitHubInstallation(BaseModel):
    """GitHub App installation."""

    id: int
    account: dict[str, Any] = Field(default_factory=dict)
    repository_selection: str = "all"
    access_tokens_url: str = ""
    repositories_url: str = ""
    html_url: str = ""
    app_id: int = 0
    target_type: str = ""
    permissions: dict[str, str] = Field(default_factory=dict)
    events: list[str] = Field(default_factory=list)


class GitHubClient:
    """GitHub App client for API operations."""

    def __init__(
        self,
        app_id: str | None = None,
        private_key: str | None = None,
    ) -> None:
        """Initialize GitHub App client.

        Args:
            app_id: GitHub App ID (defaults to settings)
            private_key: GitHub App private key or path to .pem file (defaults to settings)
        """
        self.app_id = app_id or settings.github_app_id
        self.private_key = _load_private_key(private_key or settings.github_app_private_key)
        self._token_cache: dict[int, tuple[str, float]] = {}

    def _generate_jwt(self) -> str:
        """Generate JWT for GitHub App authentication."""
        if not self.app_id or not self.private_key:
            raise ValueError("GitHub App ID and private key are required")

        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + 600,
            "iss": self.app_id,
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    async def get_installation_token(self, installation_id: int) -> str:
        """Get installation access token, using cache if valid.

        Args:
            installation_id: GitHub App installation ID

        Returns:
            Installation access token
        """
        cached = self._token_cache.get(installation_id)
        if cached:
            token, expires_at = cached
            if time.time() < expires_at - 60:
                return token

        app_jwt = self._generate_jwt()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{GITHUB_API_URL}/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            data = response.json()

        token = data["token"]
        expires_at = time.time() + 3600
        self._token_cache[installation_id] = (token, expires_at)

        logger.info(f"[GITHUB] Obtained installation token for {installation_id}")
        return token

    async def list_installations(self) -> list[GitHubInstallation]:
        """List all installations of the GitHub App.

        Returns:
            List of installations
        """
        app_jwt = self._generate_jwt()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{GITHUB_API_URL}/app/installations",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            data = response.json()

        return [GitHubInstallation(**item) for item in data]

    async def get_contents(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        path: str,
        ref: str | None = None,
    ) -> FileContent | list[FileContent]:
        """Get file or directory contents from a repository.

        Args:
            installation_id: GitHub App installation ID
            owner: Repository owner
            repo: Repository name
            path: Path to file or directory
            ref: Git ref (branch, tag, commit SHA)

        Returns:
            FileContent for files, list[FileContent] for directories
        """
        token = await self.get_installation_token(installation_id)

        params = {"ref": ref} if ref else {}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{path}",
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            data = response.json()

        if isinstance(data, list):
            return [FileContent(**item) for item in data]
        return FileContent(**data)

    async def get_file_content(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        path: str,
        ref: str | None = None,
    ) -> FileContent:
        """Get a single file's content.

        Args:
            installation_id: GitHub App installation ID
            owner: Repository owner
            repo: Repository name
            path: Path to file
            ref: Git ref (branch, tag, commit SHA)

        Returns:
            FileContent with decoded content available via decode_content()

        Raises:
            ValueError: If path is a directory
        """
        result = await self.get_contents(installation_id, owner, repo, path, ref)
        if isinstance(result, list):
            raise ValueError(f"Path '{path}' is a directory, not a file")
        return result

    async def get_tree(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        tree_sha: str = "HEAD",
        recursive: bool = True,
    ) -> dict[str, Any]:
        """Get repository tree (file listing).

        Args:
            installation_id: GitHub App installation ID
            owner: Repository owner
            repo: Repository name
            tree_sha: Tree SHA or ref (default HEAD)
            recursive: Include subdirectories

        Returns:
            Tree response with file paths
        """
        token = await self.get_installation_token(installation_id)

        params = {"recursive": "1"} if recursive else {}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/trees/{tree_sha}",
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            return response.json()

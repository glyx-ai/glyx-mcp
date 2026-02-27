"""Tests for GitHub integration."""

import base64
from unittest.mock import patch

import pytest
from pytest_httpx import HTTPXMock

from glyx_python_sdk.integrations.github import FileContent, GitHubClient

pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture
def github_client() -> GitHubClient:
    """Create a GitHub client with test credentials."""
    return GitHubClient(app_id="123456", private_key="dummy-key")


@pytest.fixture
def mock_jwt():
    """Mock JWT generation to avoid needing a real RSA key."""
    with patch.object(GitHubClient, "_generate_jwt", return_value="mock.jwt.token"):
        yield


class TestGitHubClient:
    """Tests for GitHubClient."""

    async def test_get_installation_token(self, github_client: GitHubClient, httpx_mock: HTTPXMock, mock_jwt) -> None:
        """Test getting an installation access token."""
        httpx_mock.add_response(
            url="https://api.github.com/app/installations/12345/access_tokens",
            method="POST",
            json={"token": "ghs_test_token_123", "expires_at": "2024-01-01T00:00:00Z"},
        )

        token = await github_client.get_installation_token(12345)

        assert token == "ghs_test_token_123"
        request = httpx_mock.get_request()
        assert request is not None
        assert "Bearer" in request.headers["Authorization"]

    async def test_get_installation_token_cached(
        self, github_client: GitHubClient, httpx_mock: HTTPXMock, mock_jwt
    ) -> None:
        """Test that installation tokens are cached."""
        httpx_mock.add_response(
            url="https://api.github.com/app/installations/12345/access_tokens",
            method="POST",
            json={"token": "ghs_test_token_123", "expires_at": "2024-01-01T00:00:00Z"},
        )

        token1 = await github_client.get_installation_token(12345)
        token2 = await github_client.get_installation_token(12345)

        assert token1 == token2
        assert len(httpx_mock.get_requests()) == 1

    async def test_list_installations(self, github_client: GitHubClient, httpx_mock: HTTPXMock, mock_jwt) -> None:
        """Test listing GitHub App installations."""
        httpx_mock.add_response(
            url="https://api.github.com/app/installations",
            method="GET",
            json=[
                {
                    "id": 12345,
                    "account": {"login": "test-org", "type": "Organization"},
                    "repository_selection": "all",
                    "access_tokens_url": "https://api.github.com/app/installations/12345/access_tokens",
                    "repositories_url": "https://api.github.com/installation/repositories",
                }
            ],
        )

        installations = await github_client.list_installations()

        assert len(installations) == 1
        assert installations[0].id == 12345
        assert installations[0].account["login"] == "test-org"

    async def test_get_file_content(self, github_client: GitHubClient, httpx_mock: HTTPXMock, mock_jwt) -> None:
        """Test getting file content from a repository."""
        file_content = base64.b64encode(b"# Hello World\n\nThis is a test.").decode()

        httpx_mock.add_response(
            url="https://api.github.com/app/installations/12345/access_tokens",
            method="POST",
            json={"token": "ghs_test_token_123"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/test-org/test-repo/contents/README.md",
            method="GET",
            json={
                "name": "README.md",
                "path": "README.md",
                "sha": "abc123",
                "size": 42,
                "type": "file",
                "content": file_content,
                "encoding": "base64",
                "url": "https://api.github.com/repos/test-org/test-repo/contents/README.md",
                "html_url": "https://github.com/test-org/test-repo/blob/main/README.md",
                "download_url": "https://raw.githubusercontent.com/test-org/test-repo/main/README.md",
            },
        )

        result = await github_client.get_file_content(12345, "test-org", "test-repo", "README.md")

        assert isinstance(result, FileContent)
        assert result.name == "README.md"
        assert result.type == "file"
        assert result.decode_content() == "# Hello World\n\nThis is a test."

    async def test_get_directory_contents(self, github_client: GitHubClient, httpx_mock: HTTPXMock, mock_jwt) -> None:
        """Test getting directory contents from a repository."""
        httpx_mock.add_response(
            url="https://api.github.com/app/installations/12345/access_tokens",
            method="POST",
            json={"token": "ghs_test_token_123"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/test-org/test-repo/contents/src",
            method="GET",
            json=[
                {
                    "name": "main.py",
                    "path": "src/main.py",
                    "sha": "abc123",
                    "size": 100,
                    "type": "file",
                    "url": "https://api.github.com/repos/test-org/test-repo/contents/src/main.py",
                },
                {
                    "name": "utils",
                    "path": "src/utils",
                    "sha": "def456",
                    "size": 0,
                    "type": "dir",
                    "url": "https://api.github.com/repos/test-org/test-repo/contents/src/utils",
                },
            ],
        )

        result = await github_client.get_contents(12345, "test-org", "test-repo", "src")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0].name == "main.py"
        assert result[0].type == "file"
        assert result[1].name == "utils"
        assert result[1].type == "dir"

    async def test_get_tree(self, github_client: GitHubClient, httpx_mock: HTTPXMock, mock_jwt) -> None:
        """Test getting repository tree."""
        httpx_mock.add_response(
            url="https://api.github.com/app/installations/12345/access_tokens",
            method="POST",
            json={"token": "ghs_test_token_123"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/test-org/test-repo/git/trees/HEAD?recursive=1",
            method="GET",
            json={
                "sha": "abc123",
                "url": "https://api.github.com/repos/test-org/test-repo/git/trees/abc123",
                "tree": [
                    {"path": "README.md", "mode": "100644", "type": "blob", "sha": "def456", "size": 42},
                    {"path": "src", "mode": "040000", "type": "tree", "sha": "ghi789"},
                    {"path": "src/main.py", "mode": "100644", "type": "blob", "sha": "jkl012", "size": 100},
                ],
                "truncated": False,
            },
        )

        result = await github_client.get_tree(12345, "test-org", "test-repo", recursive=True)

        assert result["sha"] == "abc123"
        assert len(result["tree"]) == 3
        assert result["tree"][0]["path"] == "README.md"

    async def test_get_file_content_with_ref(
        self, github_client: GitHubClient, httpx_mock: HTTPXMock, mock_jwt
    ) -> None:
        """Test getting file content with a specific ref."""
        file_content = base64.b64encode(b"v2 content").decode()

        httpx_mock.add_response(
            url="https://api.github.com/app/installations/12345/access_tokens",
            method="POST",
            json={"token": "ghs_test_token_123"},
        )
        httpx_mock.add_response(
            method="GET",
            json={
                "name": "README.md",
                "path": "README.md",
                "sha": "abc123",
                "size": 10,
                "type": "file",
                "content": file_content,
                "encoding": "base64",
                "url": "https://api.github.com/repos/test-org/test-repo/contents/README.md",
            },
        )

        result = await github_client.get_file_content(12345, "test-org", "test-repo", "README.md", ref="v2.0.0")

        assert result.decode_content() == "v2 content"
        request = httpx_mock.get_requests()[-1]
        assert b"ref=v2.0.0" in request.url.query

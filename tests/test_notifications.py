"""Unit tests for NotificationService."""

from unittest.mock import MagicMock, patch
import sys
import pytest

# Mock knockapi before importing api.notifications
mock_knock_module = MagicMock()
sys.modules["knockapi"] = mock_knock_module

# Mock settings
mock_settings_module = MagicMock()
mock_settings = MagicMock()
mock_settings.knock_api_key = "test-key"
mock_settings_module.settings = mock_settings
sys.modules["glyx_python_sdk.settings"] = mock_settings_module

from api.notifications import NotificationService  # noqa: E402
from api.models.notifications import TaskNotificationPayload, GitHubNotificationPayload  # noqa: E402


@pytest.fixture
def mock_knock():
    """Mock Knock client."""
    with patch("api.notifications.Knock") as mock:
        yield mock


@pytest.fixture
def notification_service(mock_knock):
    """Create NotificationService with mocked client."""
    # Ensure settings.knock_api_key is set so client is initialized
    with patch("api.notifications.settings") as mock_settings:
        mock_settings.knock_api_key = "test-key"
        service = NotificationService()
        return service


@pytest.mark.asyncio
async def test_send_task_notification(notification_service):
    """Test sending task notification."""
    payload = TaskNotificationPayload(
        task_id="task-123",
        title="Test Task",
        description="This is a test task",
        status="in_progress",
        assignee_id="user-456",
        url="/tasks/task-123",
    )

    await notification_service.send_task_notification(payload)

    notification_service.client.workflows.trigger.assert_called_once_with(
        key="task-created",
        recipients=["user-456"],
        data={
            "task_id": "task-123",
            "title": "Test Task",
            "description": "This is a test task",
            "status": "in_progress",
            "assignee_id": "user-456",
            "url": "/tasks/task-123",
        },
    )


@pytest.mark.asyncio
async def test_send_github_notification(notification_service):
    """Test sending GitHub notification."""
    payload = GitHubNotificationPayload(
        event_type="github.push",
        actor="octocat",
        repo="octocat/Hello-World",
        content="Pushed 3 commits",
        url="https://github.com/octocat/Hello-World",
        metadata={"commits": 3},
    )

    await notification_service.send_github_notification(payload)

    notification_service.client.workflows.trigger.assert_called_once_with(
        key="github-activity",
        recipients=["github-channel"],
        data={
            "event_type": "github.push",
            "actor": "octocat",
            "repo": "octocat/Hello-World",
            "content": "Pushed 3 commits",
            "url": "https://github.com/octocat/Hello-World",
            "metadata": {"commits": 3},
        },
    )


@pytest.mark.asyncio
async def test_initialization_without_key():
    """Test initialization without API key."""
    with patch("api.notifications.settings") as mock_settings:
        mock_settings.knock_api_key = None
        service = NotificationService()
        assert service.client is None

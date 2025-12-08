import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from api.webhooks.linear import process_linear_event, handle_issue_event
from api.models.linear import LinearIssue, LinearWebhookPayload


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def mock_notification_service():
    with patch("api.notifications.notification_service") as mock:
        mock.send_feature_notification = AsyncMock()
        yield mock


@pytest.mark.asyncio
async def test_handle_issue_event_create(mock_supabase, mock_notification_service):
    """Test handling of issue create event with Pydantic model."""
    issue = LinearIssue(
        id="issue-id",
        identifier="GLYX-123",
        title="Test Issue",
        priority=1,
        teamId="team-id",
        stateId="state-id",
        url="http://linear.app/issue/GLYX-123",
    )

    result = await handle_issue_event("create", issue, mock_supabase)

    assert "Processed Issue create: GLYX-123" in result
    mock_notification_service.send_feature_notification.assert_called_once_with(
        event="linear.issue.create", feature_name="Test Issue", linear_info="GLYX-123: Test Issue (Priority: 1)"
    )


@pytest.mark.asyncio
async def test_process_linear_event_routing(mock_supabase):
    """Test routing of generic event types."""
    with patch("api.webhooks.linear.handle_issue_event", new_callable=AsyncMock) as mock_issue_handler:
        mock_issue_handler.return_value = "Handled Issue"

        # Test Issue event (mock settings to avoid error)
        with patch("api.webhooks.linear.settings") as mock_settings:
            mock_settings.linear_api_key = "dummy"

            payload = {
                "action": "create",
                "type": "Issue",
                "createdAt": "2023-10-27T10:00:00Z",
                "data": {
                    "id": "issue-id",
                    "identifier": "GLYX-123",
                    "title": "Test Issue",
                    "priority": 1,
                    "teamId": "team-id",
                    "stateId": "state-id",
                    "url": "http://linear.app/issue/GLYX-123",
                },
            }
            # process_linear_event expects the dict, which it then parses
            result = await process_linear_event(payload, mock_supabase)

            assert result == "Handled Issue"
            # Verify it was called with specific args - arg[0] is action, arg[1] is issue model
            args = mock_issue_handler.call_args[0]
            assert args[0] == "create"
            assert isinstance(args[1], LinearIssue)
            assert args[1].identifier == "GLYX-123"

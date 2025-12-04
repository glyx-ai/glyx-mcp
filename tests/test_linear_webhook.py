"""Tests for Linear webhook integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from glyx_python_sdk.integrations.linear import AgentSessionEvent, LinearGraphQLClient
from api.webhooks.base import verify_signature


def test_agent_session_event_parsing():
    """Test parsing of AgentSessionEvent payload."""
    payload = {
        "action": "session.created",
        "sessionId": "session-123",
        "workspaceId": "workspace-456",
        "organizationId": "org-789",
        "data": {"task": "Test task"},
        "timestamp": "2024-01-01T00:00:00Z",
    }

    event = AgentSessionEvent(
        action=payload["action"],
        session_id=payload["sessionId"],
        workspace_id=payload["workspaceId"],
        organization_id=payload["organizationId"],
        data=payload["data"],
        timestamp=payload["timestamp"],
    )

    assert event.action == "session.created"
    assert event.session_id == "session-123"
    assert event.workspace_id == "workspace-456"
    assert event.organization_id == "org-789"


def test_verify_signature():
    """Test webhook signature verification."""
    secret = "test-secret"
    payload = b'{"test": "data"}'
    signature = "sha256=" + "a" * 64

    result = verify_signature(payload, signature, secret)
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_linear_client_emit_activity():
    """Test Linear GraphQL client activity emission."""
    client = LinearGraphQLClient("test-api-key")

    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"agentActivityCreate": {"success": True}}}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value = mock_client_instance

        result = await client.emit_activity("session-123", "thought", "Test content")

        assert "data" in result
        mock_client_instance.post.assert_called_once()


@pytest.mark.asyncio
async def test_linear_client_acknowledge_session():
    """Test session acknowledgment."""
    client = LinearGraphQLClient("test-api-key")

    with patch.object(client, "emit_activity") as mock_emit:
        await client.acknowledge_session("session-123", "Processing...")
        mock_emit.assert_called_once_with("session-123", "thought", "Processing...", {"acknowledged": True})

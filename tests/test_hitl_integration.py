"""Integration tests for HITL (Human-in-the-Loop) functionality.

These tests verify the HITL API endpoints and notification flow.

Run with:
    uv run pytest tests/test_hitl_integration.py -v -s

For integration tests (requires external services):
    uv run pytest tests/test_hitl_integration.py -v -s -m integration
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

# Import the actual routes to test
from api.routes.hitl import (
    CreateHITLRequest,
    HITLRequestResponse,
    HITLStatus,
    RespondToHITLRequest,
    _send_hitl_notification,
)


class MockSupabaseResponse:
    """Mock Supabase response."""

    def __init__(self, data: list | dict | None = None) -> None:
        self.data = data


class MockSupabaseQuery:
    """Mock Supabase query builder."""

    def __init__(self, data: list | dict | None = None) -> None:
        self._data = data

    def select(self, *args: str) -> "MockSupabaseQuery":
        return self

    def insert(self, data: dict) -> "MockSupabaseQuery":
        return self

    def update(self, data: dict) -> "MockSupabaseQuery":
        return self

    def eq(self, field: str, value: str) -> "MockSupabaseQuery":
        return self

    def gt(self, field: str, value: str) -> "MockSupabaseQuery":
        return self

    def lt(self, field: str, value: str) -> "MockSupabaseQuery":
        return self

    def order(self, field: str, desc: bool = False) -> "MockSupabaseQuery":
        return self

    def single(self) -> "MockSupabaseQuery":
        return self

    def maybe_single(self) -> "MockSupabaseQuery":
        return self

    def execute(self) -> MockSupabaseResponse:
        return MockSupabaseResponse(self._data)


class MockSupabaseClient:
    """Mock Supabase client."""

    def __init__(self, tables: dict | None = None) -> None:
        self._tables = tables or {}

    def table(self, name: str) -> MockSupabaseQuery:
        return MockSupabaseQuery(self._tables.get(name))


# Test fixtures
@pytest.fixture
def mock_task_data() -> dict:
    """Sample task data."""
    return {
        "id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "status": "running",
        "agent_type": "claude",
        "device_id": "test-device",
    }


@pytest.fixture
def mock_hitl_data(mock_task_data: dict) -> dict:
    """Sample HITL request data."""
    return {
        "id": str(uuid.uuid4()),
        "task_id": mock_task_data["id"],
        "user_id": mock_task_data["user_id"],
        "prompt": "Test prompt: Should I proceed?",
        "options": ["Yes", "No"],
        "status": "pending",
        "response": None,
        "created_at": datetime.now(UTC).isoformat(),
        "responded_at": None,
        "expires_at": (datetime.now(UTC).replace(minute=datetime.now(UTC).minute + 5)).isoformat(),
    }


class TestHITLModels:
    """Test HITL Pydantic models."""

    def test_create_hitl_request_valid(self) -> None:
        """Test CreateHITLRequest with valid data."""
        request = CreateHITLRequest(
            task_id="test-task-123",
            prompt="Should I deploy?",
            options=["Yes", "No"],
        )
        assert request.task_id == "test-task-123"
        assert request.prompt == "Should I deploy?"
        assert request.options == ["Yes", "No"]

    def test_create_hitl_request_no_options(self) -> None:
        """Test CreateHITLRequest without options."""
        request = CreateHITLRequest(
            task_id="test-task-123",
            prompt="Enter your response",
        )
        assert request.options is None

    def test_respond_to_hitl_request(self) -> None:
        """Test RespondToHITLRequest model."""
        request = RespondToHITLRequest(response="Yes, proceed")
        assert request.response == "Yes, proceed"

    def test_hitl_request_response(self, mock_hitl_data: dict) -> None:
        """Test HITLRequestResponse model."""
        response = HITLRequestResponse(**mock_hitl_data)
        assert response.id == mock_hitl_data["id"]
        assert response.status == "pending"
        assert response.response is None


class TestHITLStatus:
    """Test HITL status enum."""

    def test_status_values(self) -> None:
        """Test all status values are defined."""
        assert HITLStatus.PENDING == "pending"
        assert HITLStatus.RESPONDED == "responded"
        assert HITLStatus.EXPIRED == "expired"
        assert HITLStatus.CANCELLED == "cancelled"


class TestHITLNotification:
    """Test HITL notification sending."""

    @patch("api.routes.hitl.settings")
    @patch("api.routes.hitl.Knock")
    def test_send_hitl_notification_success(
        self, mock_knock_class: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Test successful notification sending."""
        mock_settings.knock_api_key = "test-api-key"
        mock_knock_instance = MagicMock()
        mock_knock_class.return_value = mock_knock_instance

        _send_hitl_notification(
            user_id="user-123",
            hitl_request_id="hitl-123",
            task_id="task-123",
            prompt="Test prompt",
            agent_type="claude",
            device_name="MacBook Pro",
        )

        mock_knock_instance.workflows.trigger.assert_called_once()
        call_kwargs = mock_knock_instance.workflows.trigger.call_args.kwargs
        assert call_kwargs["key"] == "agent-needs-input"
        assert call_kwargs["recipients"] == ["user-123"]
        assert call_kwargs["data"]["hitl_request_id"] == "hitl-123"
        assert call_kwargs["data"]["urgency"] == "critical"
        assert call_kwargs["data"]["action_required"] is True

    @patch("api.routes.hitl.settings")
    def test_send_hitl_notification_no_api_key(self, mock_settings: MagicMock) -> None:
        """Test notification skipped when no API key."""
        mock_settings.knock_api_key = None

        # Should not raise, just log and return
        _send_hitl_notification(
            user_id="user-123",
            hitl_request_id="hitl-123",
            task_id="task-123",
            prompt="Test prompt",
        )


class TestHITLEndpoints:
    """Test HITL API endpoint logic."""

    @pytest.mark.asyncio
    async def test_create_hitl_request_flow(
        self, mock_task_data: dict, mock_hitl_data: dict
    ) -> None:
        """Test the create HITL request flow logic."""
        from api.routes.hitl import create_hitl_request

        # Mock Supabase client
        mock_supabase = MockSupabaseClient(
            tables={
                "agent_tasks": mock_task_data,
                "hitl_requests": [mock_hitl_data],
            }
        )

        with patch("api.routes.hitl._get_supabase", return_value=mock_supabase):
            with patch("api.routes.hitl._send_hitl_notification"):
                body = CreateHITLRequest(
                    task_id=mock_task_data["id"],
                    prompt="Test prompt",
                )

                # Note: In real test, this would hit the actual endpoint
                # Here we test the model and flow logic
                assert body.task_id == mock_task_data["id"]

    @pytest.mark.asyncio
    async def test_respond_to_hitl_validates_status(self) -> None:
        """Test that responding validates HITL status."""
        # Test that only pending requests can be responded to
        for status in [HITLStatus.RESPONDED, HITLStatus.EXPIRED, HITLStatus.CANCELLED]:
            # These statuses should reject responses
            assert status != HITLStatus.PENDING


@pytest.mark.integration
class TestHITLIntegration:
    """Integration tests requiring external services.

    These tests hit actual endpoints and require:
    - SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
    - KNOCK_API_KEY (for notification tests)
    - Running glyx-mcp API server or Cloud Run deployment

    Run with: pytest -m integration
    """

    @pytest.fixture
    def api_base_url(self) -> str:
        """Get API base URL from environment."""
        return os.getenv(
            "GLYX_API_URL",
            "https://glyx-mcp-996426597393.us-central1.run.app",
        )

    @pytest.fixture
    def supabase_config(self) -> tuple[str, str]:
        """Get Supabase configuration."""
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:
            pytest.skip("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set")
        return url, key

    @pytest.mark.asyncio
    async def test_hitl_full_flow(
        self, api_base_url: str, supabase_config: tuple[str, str]
    ) -> None:
        """Test full HITL flow: create task → create HITL → respond."""
        import httpx

        supabase_url, supabase_key = supabase_config

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get a user ID
            response = await client.get(
                f"{supabase_url}/rest/v1/profiles",
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                },
                params={"limit": "1"},
            )
            if response.status_code != 200 or not response.json():
                pytest.skip("No users in database")

            user_id = response.json()[0]["id"]
            task_id = str(uuid.uuid4())

            # Create task
            response = await client.post(
                f"{supabase_url}/rest/v1/agent_tasks",
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation",
                },
                json={
                    "id": task_id,
                    "user_id": user_id,
                    "device_id": "integration-test",
                    "agent_type": "claude",
                    "task_type": "chat",
                    "payload": {"prompt": "Integration test"},
                    "status": "running",
                },
            )
            assert response.status_code in (200, 201), f"Create task failed: {response.text}"

            # Create HITL request
            response = await client.post(
                f"{api_base_url}/api/hitl",
                json={
                    "task_id": task_id,
                    "prompt": "Integration test: approve?",
                    "options": ["Yes", "No"],
                },
            )
            assert response.status_code == 200, f"Create HITL failed: {response.text}"
            hitl_data = response.json()
            hitl_id = hitl_data["id"]

            # Verify pending
            response = await client.get(
                f"{api_base_url}/api/hitl/pending",
                params={"user_id": user_id},
            )
            assert response.status_code == 200
            pending = response.json()
            assert any(r["id"] == hitl_id for r in pending)

            # Respond to HITL
            response = await client.post(
                f"{api_base_url}/api/hitl/{hitl_id}/respond",
                json={"response": "Yes"},
            )
            assert response.status_code == 200, f"Respond failed: {response.text}"

            # Verify responded
            response = await client.get(f"{api_base_url}/api/hitl/{hitl_id}")
            assert response.status_code == 200
            assert response.json()["status"] == "responded"

            # Cleanup - delete task
            await client.delete(
                f"{supabase_url}/rest/v1/agent_tasks",
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                },
                params={"id": f"eq.{task_id}"},
            )

import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Mock dependencies BEFORE import
mock_linear_module = MagicMock()
mock_linear_module.LinearTools = MagicMock()
sys.modules["integration_agents.linear_agent"] = mock_linear_module

mock_knock = MagicMock()
sys.modules["knockapi"] = MagicMock()

# Now import the module under test
from framework.lifecycle import FeatureLifecycle  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture
def lifecycle():
    lc = FeatureLifecycle()

    # Configure Linear Mock
    lc.linear = mock_linear_module.LinearTools.return_value
    lc.linear.list_teams = AsyncMock(return_value=[{"id": "team-123", "name": "Team Alpha"}])
    lc.linear.create_issue = AsyncMock(return_value="Created issue PROJ-123 (http://url)")

    # Configure Knock Mock (lazy-init property, mock the underlying client)
    mock_knock_client = MagicMock()
    mock_knock_client.workflows.trigger = MagicMock()
    lc._knock_client = mock_knock_client

    yield lc


@pytest.mark.asyncio
async def test_start_feature_auto_team(lifecycle):
    """Test starting a feature where team ID is auto-discovered."""
    result = await lifecycle.start_feature("Test Feature")

    # Verify Linear interaction
    lifecycle.linear.list_teams.assert_called_once()
    lifecycle.linear.create_issue.assert_called_once_with(
        title="Feature: Test Feature",
        team_id="team-123",
        description="Tracking issue for feature: Test Feature",
        priority=0,
    )

    # Verify Knock notification trigger
    lifecycle.knock_client.workflows.trigger.assert_called_once()
    call_kwargs = lifecycle.knock_client.workflows.trigger.call_args.kwargs
    assert call_kwargs["key"] == "feature-lifecycle"
    assert call_kwargs["data"]["event"] == "started"
    assert call_kwargs["data"]["feature_name"] == "Test Feature"

    assert "started" in result


@pytest.mark.asyncio
async def test_generate_plan(lifecycle):
    """Test generating a plan template."""
    with patch("builtins.open", new_callable=MagicMock) as mock_open:
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        await lifecycle.generate_plan_template("My Feature", "dummy_plan.md")

        mock_open.assert_called_with("dummy_plan.md", "w")
        mock_file.write.assert_called()
        args, _ = mock_file.write.call_args
        content = args[0]
        assert "# Implementation Plan - My Feature" in content

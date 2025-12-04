"""Linear webhook handler for glyx-mcp."""

import logging
from typing import Any

from api.integrations.linear import LinearGraphQLClient, handle_session_task
from glyx_python_sdk import settings
from api.webhooks.base import WebhookConfig, create_webhook_router, log_webhook_event

logger = logging.getLogger(__name__)


async def handle_session_created(
    payload: dict,
    session_id: str,
    workspace_id: str,
    supabase_client: Any,
    linear_client: LinearGraphQLClient,
) -> str:
    """Handle session.created events - acknowledge within 10 seconds and create orchestration task."""
    logger.info(f"Handling session.created for session {session_id}")

    await linear_client.acknowledge_session(session_id, "Session received, initializing...")
    logger.info(f"Acknowledged session {session_id}")

    task_description = payload.get("data", {}).get("task", "") or payload.get("data", {}).get("description", "")
    if task_description:
        task_id = await handle_session_task(
            supabase_client,
            linear_client,
            session_id=session_id,
            workspace_id=workspace_id,
            task_description=task_description,
            organization_id=payload.get("organizationId", ""),
        )
        logger.info(f"Created orchestration task {task_id} for session {session_id}")
        return f"Session {session_id} acknowledged and task created"

    return f"Session {session_id} acknowledged"


async def handle_session_updated(
    payload: dict,
    session_id: str,
    supabase_client: Any,
) -> str:
    """Handle session.updated events."""
    logger.info(f"Handling session.updated for session {session_id}")
    return f"Session {session_id} updated"


async def process_linear_event(payload: dict, supabase: Any) -> str:
    """Process a Linear webhook event."""
    event = payload.get("_event_type", "")
    session_id = payload.get("sessionId", "")
    workspace_id = payload.get("workspaceId", "")

    if not settings.linear_api_key:
        raise ValueError("Linear API key not configured")

    linear_client = LinearGraphQLClient(settings.linear_api_key)

    if event == "session.created":
        return await handle_session_created(payload, session_id, workspace_id, supabase, linear_client)
    elif event == "session.updated":
        return await handle_session_updated(payload, session_id, supabase)

    logger.info(f"Unhandled Linear event: {event}")
    return f"Event {event} received"


def create_linear_webhook_router(get_supabase_fn) -> Any:
    """Create Linear webhook router with Supabase client factory."""
    config = WebhookConfig(
        name="linear",
        signature_header="X-Linear-Signature",
        event_header="X-Linear-Event",
        secret_setting="linear_webhook_secret",
        log_table="linear_webhook_events",
        health_check=lambda: {"api_key_configured": bool(settings.linear_api_key)},
    )

    async def linear_event_handler(payload: dict, supabase: Any) -> str:
        """Handle Linear webhook event."""
        event = payload.get("_event_type", "")
        session_id = payload.get("sessionId", "")

        log_webhook_event(
            supabase,
            config,
            event,
            payload,
            metadata={"session_id": session_id},
        )

        return await process_linear_event(payload, supabase)

    def get_secret(setting_name: str) -> str | None:
        """Get secret from settings."""
        return getattr(settings, setting_name, None)

    return create_webhook_router(
        config=config,
        get_supabase_fn=get_supabase_fn,
        get_secret_fn=get_secret,
        process_event=linear_event_handler,
    )

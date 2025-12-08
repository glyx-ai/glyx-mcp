"""Linear webhook handler for glyx-mcp."""

import logging
from typing import Any

from api.integrations.linear import handle_session_task
from glyx_python_sdk import settings
from api.webhooks.base import WebhookConfig, create_webhook_router, log_webhook_event
from api.models.linear import LinearWebhookPayload, LinearIssue, LinearProject

logger = logging.getLogger(__name__)


async def handle_session_created(
    payload: dict,
    session_id: str,
    workspace_id: str,
    supabase_client: Any,
    linear_client: Any,
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
    # We parse the base structure first to identify the type
    # Note: 'LinearWebhookPayload' assumes a standard structure.
    # Linear sends 'action', 'type', 'data' etc.
    try:
        # Pydantic will validate the top-level structure
        webhook_data = LinearWebhookPayload(**payload)
        event_type = webhook_data.type

        # Manually extract session logic if needed, or rely on payload
        # existing logic used '_event_type' which might be from a specific header/middleware?
        # Assuming 'type' field in payload maps to 'Issue', 'Project' etc.

        # Fallback for previous session logic variables
        session_id = payload.get("sessionId", "")  # Not standard Linear payload?
        workspace_id = payload.get("workspaceId", "")  # Not standard?

    except Exception as e:
        # Fallback or error logging if payload doesn't match generic Linear structure
        logger.warning(f"Failed to parse Linear payload as model: {e}")
        # Proceed with legacy dict access for backward compatibility or special events if necessary
        event_type = payload.get("_event_type", "")
        session_id = payload.get("sessionId", "")
        workspace_id = payload.get("workspaceId", "")
        webhook_data = None

    if not settings.linear_api_key:
        raise ValueError("Linear API key not configured")

    from api.integrations.linear import LinearGraphQLClient

    linear_client = LinearGraphQLClient(settings.linear_api_key)

    if event_type == "Issue" and webhook_data:
        # Parse data as LinearIssue
        issue_data = LinearIssue(**webhook_data.data)
        return await handle_issue_event(webhook_data.action, issue_data, supabase)

    elif event_type == "Project" and webhook_data:
        # We can implement LinearProject model parsing similarly
        return await handle_project_event(webhook_data.action, webhook_data.data, supabase)

    # Maintain generic session handlers
    elif event_type == "session.created":
        return await handle_session_created(payload, session_id, workspace_id, supabase, linear_client)

    logger.info(f"Unhandled Linear event: {event_type}")
    return f"Event {event_type} received"


async def handle_issue_event(action: str, issue: LinearIssue, supabase: Any) -> str:
    """Handle Issue events (create, update)."""
    # Notify via NotificationService
    from api.notifications import notification_service

    # Map Linear action to logical event
    # If priority is high (1) or urgent (0), notify logic might trigger
    if action == "create" or (action == "update" and issue.priority <= 1):
        await notification_service.send_feature_notification(
            event=f"linear.issue.{action}",
            feature_name=issue.title,
            linear_info=f"{issue.identifier}: {issue.title} (Priority: {issue.priority})",
        )

    return f"Processed Issue {action}: {issue.identifier}"


async def handle_project_event(action: str, data: dict, supabase: Any) -> str:
    """Handle Project events."""
    name = data.get("name", "Unknown")
    return f"Processed Project {action}: {name}"


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
        # Inject custom fields if the router middleware added them
        # Logic in generic router might strip standard payload, so be careful.

        # Assuming payload is the raw JSON body parsed to dict

        # We might need to handle the header extraction if previous logic used headers for _event_type
        # If 'WebhookConfig' passes 'event_header' value into payload as '_event_type', we use that or the body 'type'

        event = payload.get("_event_type") or payload.get("type", "")

        # Ensure payload acts as valid input for our models
        # If _event_type was injected, we might need to clean it or handle it

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

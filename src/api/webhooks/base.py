"""Generic webhook handler for multiple providers."""

import hashlib
import hmac
import logging
import os
from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

WEBHOOK_TEST_MODE = os.environ.get("WEBHOOK_TEST_MODE", "").lower() == "true"


class WebhookResponse(BaseModel):
    success: bool
    event: str
    message: str = ""
    metadata: dict[str, Any] = {}


class WebhookConfig:
    """Configuration for a webhook provider."""

    def __init__(
        self,
        name: str,
        signature_header: str,
        event_header: str,
        secret_setting: str,
        log_table: str,
        health_check: Callable[[], dict] | None = None,
    ):
        """Initialize webhook configuration.

        Args:
            name: Provider name (e.g., "github", "linear")
            signature_header: Header name for signature (e.g., "X-Hub-Signature-256")
            event_header: Header name for event type (e.g., "X-GitHub-Event")
            secret_setting: Setting name for webhook secret (e.g., "github_webhook_secret")
            log_table: Supabase table name for logging events
            health_check: Optional function to check provider health
        """
        self.name = name
        self.signature_header = signature_header
        self.event_header = event_header
        self.secret_setting = secret_setting
        self.log_table = log_table
        self.health_check = health_check


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify webhook signature using HMAC SHA256."""
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def log_webhook_event(
    supabase_client: Any,
    config: WebhookConfig,
    event_type: str,
    payload: dict,
    processed: bool = True,
    error: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Log webhook event to database."""
    log_data = {
        "event_type": event_type,
        "payload": payload,
        "processed": processed,
        "processed_at": datetime.now().isoformat() if processed else None,
        "error": error,
    }
    if metadata:
        log_data.update(metadata)

    supabase_client.table(config.log_table).insert(log_data).execute()


def create_webhook_router(
    config: WebhookConfig,
    get_supabase_fn: Callable[[], Any],
    get_secret_fn: Callable[[str], str | None],
    process_event: Callable[[dict, Any], Any],
    parse_event: Callable[[dict, str], dict[str, Any]] | None = None,
) -> APIRouter:
    """Create a generic webhook router for a provider.

    Args:
        config: Webhook configuration
        get_supabase_fn: Function to get Supabase client
        get_secret_fn: Function to get webhook secret from settings
        process_event: Function to process webhook events (takes payload, supabase)
        parse_event: Optional function to parse/validate event payload

    Returns:
        Configured APIRouter
    """
    router = APIRouter(prefix="/webhooks", tags=["webhooks"])

    @router.post(f"/{config.name}", response_model=WebhookResponse)
    async def webhook_handler(
        request: Request,
        signature: str | None = Header(None, alias=config.signature_header),
        event: str | None = Header(None, alias=config.event_header),
    ) -> WebhookResponse:
        """Handle webhook events for the provider."""
        if not event:
            raise HTTPException(status_code=400, detail=f"Missing {config.event_header} header")

        body = await request.body()

        if not WEBHOOK_TEST_MODE:
            if not signature:
                raise HTTPException(status_code=400, detail=f"Missing {config.signature_header} header")

            secret = get_secret_fn(config.secret_setting)
            if not secret:
                raise HTTPException(status_code=500, detail=f"{config.name.title()} webhook not configured")

            if not verify_signature(body, signature, secret):
                raise HTTPException(status_code=401, detail="Invalid signature")

        payload = await request.json()
        supabase = get_supabase_fn()

        if parse_event:
            event_data = parse_event(payload, event)
            payload.update(event_data)

        payload["_event_type"] = event

        try:
            message = await process_event(payload, supabase)

            log_webhook_event(supabase, config, event, payload, processed=True)
            return WebhookResponse(success=True, event=event, message=message)
        except Exception as e:
            logger.exception(f"Error processing {config.name} event {event}")
            log_webhook_event(supabase, config, event, payload, processed=False, error=str(e))
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(f"/{config.name}/health")
    async def webhook_health() -> dict:
        """Health check for webhook endpoint."""
        health_status = {
            "status": "ok",
            "configured": bool(get_secret_fn(config.secret_setting)),
        }
        if config.health_check:
            health_status.update(config.health_check())
        return health_status

    return router

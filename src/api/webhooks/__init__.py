"""Webhook handlers for glyx-mcp."""

from api.webhooks.github import create_github_webhook_router
from api.webhooks.linear import create_linear_webhook_router

__all__ = ["create_github_webhook_router", "create_linear_webhook_router"]

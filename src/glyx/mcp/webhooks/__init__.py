"""Webhook handlers for glyx-mcp."""

from glyx.mcp.webhooks.github import create_github_webhook_router

__all__ = ["create_github_webhook_router"]

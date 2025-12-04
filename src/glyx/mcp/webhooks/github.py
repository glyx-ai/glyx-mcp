"""GitHub webhook handler for glyx-mcp."""

import hashlib
import hmac
import logging
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from glyx.mcp.settings import settings

logger = logging.getLogger(__name__)

# Test mode flag - set WEBHOOK_TEST_MODE=true to skip signature verification
WEBHOOK_TEST_MODE = os.environ.get("WEBHOOK_TEST_MODE", "").lower() == "true"

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookResponse(BaseModel):
    success: bool
    event: str
    delivery_id: str | None = None
    message: str | None = None


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature."""
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def get_account_name(account: dict | None) -> str:
    """Extract account name from installation account."""
    if not account:
        return "unknown"
    return str(account.get("login") or account.get("name") or account.get("slug") or "unknown")


def get_installation_id(payload: dict) -> int | None:
    """Extract installation ID from payload."""
    installation = payload.get("installation")
    if isinstance(installation, dict):
        return installation.get("id")
    return None


async def create_activity(
    supabase_client: Any,
    event_type: str,
    actor: str,
    content: str,
    org_id: str,
    org_name: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Create an activity record in Supabase."""
    try:
        supabase_client.table("activities").insert({
            "type": event_type,
            "actor": actor,
            "content": content,
            "org_id": org_id,
            "org_name": org_name,
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat(),
        }).execute()
        logger.info(f"Created activity: {event_type} by {actor}")
    except Exception as e:
        logger.error(f"Failed to create activity: {e}")


async def log_webhook_event(
    supabase_client: Any,
    event_type: str,
    action: str | None,
    installation_id: int | None,
    payload: dict,
    processed: bool = True,
    error: str | None = None,
) -> None:
    """Log webhook event to database."""
    try:
        supabase_client.table("github_webhook_events").insert({
            "event_type": event_type,
            "action": action,
            "installation_id": installation_id,
            "payload": payload,
            "processed": processed,
            "processed_at": datetime.now().isoformat() if processed else None,
            "error": error,
        }).execute()
    except Exception as e:
        logger.error(f"Failed to log webhook event: {e}")


async def handle_installation(payload: dict, action: str, supabase_client: Any) -> str:
    """Handle installation events."""
    installation = payload.get("installation", {})
    account = installation.get("account", {})
    account_name = get_account_name(account)

    if action == "created":
        await create_activity(
            supabase_client,
            event_type="github.app.installed",
            actor="github",
            content=f"GitHub App installed on {account_name}",
            org_id=str(installation.get("id", "unknown")),
            org_name=account_name,
            metadata={"installation_id": installation.get("id"), "account": account},
        )
        return f"App installed on {account_name}"
    elif action == "deleted":
        await create_activity(
            supabase_client,
            event_type="github.app.uninstalled",
            actor="github",
            content=f"GitHub App uninstalled from {account_name}",
            org_id=str(installation.get("id", "unknown")),
            org_name=account_name,
        )
        return f"App uninstalled from {account_name}"
    return f"Installation {action}"


async def handle_push(payload: dict, supabase_client: Any) -> str:
    """Handle push events."""
    repo = payload.get("repository", {}).get("full_name", "unknown")
    pusher = payload.get("pusher", {}).get("name", "unknown")
    commits = payload.get("commits", [])
    branch = payload.get("ref", "").replace("refs/heads/", "")

    await create_activity(
        supabase_client,
        event_type="github.push",
        actor="github",
        content=f"{pusher} pushed {len(commits)} commit(s) to {repo}:{branch}",
        org_id=repo,
        org_name=repo.split("/")[0] if "/" in repo else repo,
        metadata={
            "pusher": pusher,
            "repository": repo,
            "branch": branch,
            "commits": len(commits),
            "commit_messages": [c.get("message", "")[:100] for c in commits[:5]],
        },
    )
    return f"Push to {repo}: {len(commits)} commits"


async def handle_pull_request(payload: dict, action: str, supabase_client: Any) -> str:
    """Handle pull request events."""
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {}).get("full_name", "unknown")
    author = pr.get("user", {}).get("login", "unknown")
    number = pr.get("number", 0)
    title = pr.get("title", "")

    if action in ["opened", "closed", "merged", "reopened"]:
        merged = pr.get("merged", False)
        status = "merged" if merged else action

        await create_activity(
            supabase_client,
            event_type=f"github.pr.{status}",
            actor="github",
            content=f"{author} {status} PR #{number}: {title}",
            org_id=repo,
            org_name=repo.split("/")[0] if "/" in repo else repo,
            metadata={
                "author": author,
                "repository": repo,
                "number": number,
                "title": title,
                "url": pr.get("html_url"),
                "merged": merged,
            },
        )
    return f"PR {action} on {repo}: #{number}"


async def handle_issues(payload: dict, action: str, supabase_client: Any) -> str:
    """Handle issue events."""
    issue = payload.get("issue", {})
    repo = payload.get("repository", {}).get("full_name", "unknown")
    author = issue.get("user", {}).get("login", "unknown")
    number = issue.get("number", 0)
    title = issue.get("title", "")

    if action in ["opened", "closed", "reopened"]:
        await create_activity(
            supabase_client,
            event_type=f"github.issue.{action}",
            actor="github",
            content=f"{author} {action} issue #{number}: {title}",
            org_id=repo,
            org_name=repo.split("/")[0] if "/" in repo else repo,
            metadata={
                "author": author,
                "repository": repo,
                "number": number,
                "title": title,
                "url": issue.get("html_url"),
            },
        )
    return f"Issue {action} on {repo}: #{number}"


async def handle_issue_comment(payload: dict, supabase_client: Any) -> str:
    """Handle issue comment events - check for @mentions."""
    issue = payload.get("issue", {})
    comment = payload.get("comment", {})
    repo = payload.get("repository", {}).get("full_name", "unknown")
    author = comment.get("user", {}).get("login", "unknown")
    body = comment.get("body", "")
    number = issue.get("number", 0)

    # Check for mentions that should trigger agent
    body_lower = body.lower()
    if "@julian" in body_lower or "/glyx" in body_lower:
        await create_activity(
            supabase_client,
            event_type="github.mention",
            actor="github",
            content=f"{author} mentioned @julian in #{number}: {body[:100]}",
            org_id=repo,
            org_name=repo.split("/")[0] if "/" in repo else repo,
            metadata={
                "author": author,
                "repository": repo,
                "issue_number": number,
                "comment_url": comment.get("html_url"),
                "comment_body": body[:500],
                "trigger": True,  # Flag for agent processing
            },
        )
        # TODO: Queue agent task to respond
        return f"Mention detected in {repo}#{number} - agent task queued"

    return f"Comment on {repo}#{number}"


async def handle_workflow_run(payload: dict, action: str, supabase_client: Any) -> str:
    """Handle workflow run events."""
    if action != "completed":
        return f"Workflow {action}"

    workflow = payload.get("workflow_run", {})
    repo = payload.get("repository", {}).get("full_name", "unknown")
    name = workflow.get("name", "unknown")
    conclusion = workflow.get("conclusion", "unknown")

    await create_activity(
        supabase_client,
        event_type="github.workflow.completed",
        actor="github-actions",
        content=f"Workflow '{name}' {conclusion}",
        org_id=repo,
        org_name=repo.split("/")[0] if "/" in repo else repo,
        metadata={
            "repository": repo,
            "workflow": name,
            "conclusion": conclusion,
            "url": workflow.get("html_url"),
        },
    )
    return f"Workflow {name} {conclusion}"


def create_github_webhook_router(get_supabase_fn) -> APIRouter:
    """Create GitHub webhook router with Supabase client factory."""

    @router.post("/github", response_model=WebhookResponse)
    async def github_webhook(
        request: Request,
        x_hub_signature_256: str | None = Header(None),
        x_github_event: str | None = Header(None),
        x_github_delivery: str | None = Header(None),
    ) -> WebhookResponse:
        """Handle GitHub webhook events."""
        # Validate event header (always required)
        if not x_github_event:
            raise HTTPException(status_code=400, detail="Missing X-GitHub-Event header")

        # Read body first (needed for both signature check and parsing)
        body = await request.body()

        # Skip signature verification in test mode
        if WEBHOOK_TEST_MODE:
            logger.warning("WEBHOOK_TEST_MODE enabled - signature verification skipped")
        else:
            if not x_hub_signature_256:
                raise HTTPException(status_code=400, detail="Missing X-Hub-Signature-256 header")

            webhook_secret = settings.github_webhook_secret
            if not webhook_secret:
                raise HTTPException(status_code=500, detail="GitHub webhook not configured")

            if not verify_signature(body, x_hub_signature_256, webhook_secret):
                raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse payload
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        # Get Supabase client
        supabase = get_supabase_fn()

        # Log the event
        action = payload.get("action")
        installation_id = get_installation_id(payload)
        await log_webhook_event(supabase, x_github_event, action, installation_id, payload)

        # Process event
        try:
            message = await process_event(x_github_event, action, payload, supabase)
            return WebhookResponse(
                success=True,
                event=x_github_event,
                delivery_id=x_github_delivery,
                message=message,
            )
        except Exception as e:
            logger.exception(f"Error processing {x_github_event}")
            await log_webhook_event(
                supabase, x_github_event, action, installation_id, payload,
                processed=False, error=str(e),
            )
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/github/health")
    async def github_webhook_health() -> dict:
        """Health check for GitHub webhook endpoint."""
        return {
            "status": "ok",
            "configured": bool(settings.github_webhook_secret),
        }

    return router


async def process_event(
    event: str,
    action: str | None,
    payload: dict,
    supabase_client: Any,
) -> str:
    """Process a GitHub webhook event."""
    handlers = {
        "installation": lambda: handle_installation(payload, action or "", supabase_client),
        "push": lambda: handle_push(payload, supabase_client),
        "pull_request": lambda: handle_pull_request(payload, action or "", supabase_client),
        "issues": lambda: handle_issues(payload, action or "", supabase_client),
        "issue_comment": lambda: handle_issue_comment(payload, supabase_client),
        "workflow_run": lambda: handle_workflow_run(payload, action or "", supabase_client),
    }

    handler = handlers.get(event)
    if handler:
        return await handler()

    logger.info(f"Unhandled event: {event}")
    return f"Event {event} received"

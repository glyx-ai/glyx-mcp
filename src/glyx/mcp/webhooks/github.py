"""GitHub webhook handler for glyx-mcp."""

import logging
from typing import Any

from glyx_python_sdk import settings
from glyx.mcp.webhooks.base import WebhookConfig, create_webhook_router, log_webhook_event

logger = logging.getLogger(__name__)


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
    supabase_client.table("activities").insert({
        "type": event_type,
        "actor": actor,
        "content": content,
        "org_id": org_id,
        "org_name": org_name,
        "metadata": metadata or {},
        "created_at": __import__("datetime").datetime.now().isoformat(),
    }).execute()
    logger.info(f"Created activity: {event_type} by {actor}")


async def handle_installation(payload: dict, supabase_client: Any) -> str:
    """Handle installation events."""
    action = payload.get("action", "")
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


async def handle_pull_request(payload: dict, supabase_client: Any) -> str:
    """Handle pull request events."""
    action = payload.get("action", "")
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


async def handle_issues(payload: dict, supabase_client: Any) -> str:
    """Handle issue events."""
    action = payload.get("action", "")
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
                "trigger": True,
            },
        )
        return f"Mention detected in {repo}#{number} - agent task queued"

    return f"Comment on {repo}#{number}"


async def handle_workflow_run(payload: dict, supabase_client: Any) -> str:
    """Handle workflow run events."""
    action = payload.get("action", "")
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


async def process_github_event(payload: dict, supabase_client: Any) -> str:
    """Process a GitHub webhook event."""
    event = payload.get("_event_type", "")

    handlers = {
        "installation": lambda: handle_installation(payload, supabase_client),
        "push": lambda: handle_push(payload, supabase_client),
        "pull_request": lambda: handle_pull_request(payload, supabase_client),
        "issues": lambda: handle_issues(payload, supabase_client),
        "issue_comment": lambda: handle_issue_comment(payload, supabase_client),
        "workflow_run": lambda: handle_workflow_run(payload, supabase_client),
    }

    handler = handlers.get(event)
    if handler:
        return await handler()

    logger.info(f"Unhandled GitHub event: {event}")
    return f"Event {event} received"


def create_github_webhook_router(get_supabase_fn) -> Any:
    """Create GitHub webhook router with Supabase client factory."""
    config = WebhookConfig(
        name="github",
        signature_header="X-Hub-Signature-256",
        event_header="X-GitHub-Event",
        secret_setting="github_webhook_secret",
        log_table="github_webhook_events",
    )

    async def github_event_handler(payload: dict, supabase: Any) -> str:
        """Handle GitHub webhook event with action extraction."""
        event = payload.get("_event_type", "")
        action = payload.get("action")
        installation_id = get_installation_id(payload)

        log_webhook_event(
            supabase,
            config,
            event,
            payload,
            metadata={"action": action, "installation_id": installation_id},
        )

        return await process_github_event(payload, supabase)

    def get_secret(setting_name: str) -> str | None:
        """Get secret from settings."""
        return getattr(settings, setting_name, None)

    return create_webhook_router(
        config=config,
        get_supabase_fn=get_supabase_fn,
        get_secret_fn=get_secret,
        process_event=github_event_handler,
    )

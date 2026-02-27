"""Local session management for user-scoped auth.

iOS provisions a Supabase session (access + refresh token) to the local server
during QR pairing. This module manages that session on disk and provides
token refresh capabilities.

Session file: ~/.glyx/session (JSON, 0600 permissions)
"""

from __future__ import annotations

import json
import logging
import stat
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel
from supabase import create_client

from glyx_python_sdk.settings import settings

logger = logging.getLogger(__name__)

SESSION_FILE = Path.home() / ".glyx" / "session"

# Supabase access tokens expire after 60 minutes by default.
# Refresh 10 minutes before expiry to avoid race conditions.
TOKEN_REFRESH_INTERVAL_SECONDS = 50 * 60


class AuthMode(StrEnum):
    """How the local executor authenticates with Supabase."""

    SERVICE_ROLE = "service_role"
    USER_TOKEN = "user_token"
    UNPROVISIONED = "unprovisioned"


class ProvisionStatus(StrEnum):
    """Status of the local session provisioning."""

    PROVISIONED = "provisioned"
    UNPROVISIONED = "unprovisioned"
    EXPIRED = "expired"


class SessionTokens(BaseModel):
    """Supabase session tokens stored on disk."""

    access_token: str
    refresh_token: str


class ProvisionRequest(BaseModel):
    """Request body for POST /api/auth/provision."""

    access_token: str
    refresh_token: str


class ProvisionResponse(BaseModel):
    """Response for POST /api/auth/provision."""

    status: ProvisionStatus
    user_id: str | None = None
    email: str | None = None


class ProvisionStatusResponse(BaseModel):
    """Response for GET /api/auth/provision/status."""

    status: ProvisionStatus
    user_id: str | None = None
    email: str | None = None
    has_refresh_token: bool = False


def save_session(tokens: SessionTokens) -> None:
    """Persist session tokens to ~/.glyx/session with 0600 permissions."""
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(tokens.model_dump_json())
    SESSION_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)


def load_session() -> SessionTokens | None:
    """Load session from disk. Returns None if not provisioned or corrupt."""
    if not SESSION_FILE.exists():
        return None
    try:
        return SessionTokens.model_validate_json(SESSION_FILE.read_text())
    except Exception:
        logger.warning("Corrupt session file, ignoring")
        return None


def delete_session() -> None:
    """Delete the session file."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def validate_access_token(access_token: str) -> tuple[str, str] | None:
    """Validate an access token via Supabase. Returns (user_id, email) or None."""
    try:
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        response = client.auth.get_user(access_token)
        if response.user:
            return str(response.user.id), response.user.email or ""
    except Exception:
        pass
    return None


def refresh_session(refresh_token: str) -> SessionTokens | None:
    """Refresh the session using a refresh token. Persists new tokens on success."""
    try:
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        response = client.auth.refresh_session(refresh_token)
        if not response.session:
            return None
        tokens = SessionTokens(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
        )
        save_session(tokens)
        return tokens
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        return None


def resolve_auth_mode() -> AuthMode:
    """Determine which auth mode to use based on available credentials."""
    if settings.supabase_service_role_key:
        return AuthMode.SERVICE_ROLE
    if load_session() is not None:
        return AuthMode.USER_TOKEN
    return AuthMode.UNPROVISIONED

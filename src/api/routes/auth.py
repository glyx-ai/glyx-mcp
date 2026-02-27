"""Authentication API routes."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from supabase import create_client

from api.session import (
    ProvisionRequest,
    ProvisionResponse,
    ProvisionStatus,
    ProvisionStatusResponse,
    SessionTokens,
    delete_session,
    load_session,
    refresh_session,
    save_session,
    validate_access_token,
)
from glyx_python_sdk.settings import settings
from glyx_python_sdk.types import AuthResponse, AuthSignInRequest, AuthSignUpRequest

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Standard auth endpoints
# ---------------------------------------------------------------------------


@router.post("/signup")
async def api_auth_signup(body: AuthSignUpRequest) -> AuthResponse:
    """Sign up a new user via Supabase Auth."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    options = {"data": body.metadata} if body.metadata else None
    response = client.auth.sign_up({"email": body.email, "password": body.password, "options": options})
    user = response.user
    session = response.session
    return AuthResponse(
        user_id=user.id if user else None,
        email=user.email if user else None,
        access_token=session.access_token if session else None,
        refresh_token=session.refresh_token if session else None,
        expires_at=session.expires_at if session else None,
    )


@router.post("/signin")
async def api_auth_signin(body: AuthSignInRequest) -> AuthResponse:
    """Sign in a user via Supabase Auth."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    response = client.auth.sign_in_with_password({"email": body.email, "password": body.password})
    user = response.user
    session = response.session
    return AuthResponse(
        user_id=user.id if user else None,
        email=user.email if user else None,
        access_token=session.access_token if session else None,
        refresh_token=session.refresh_token if session else None,
        expires_at=session.expires_at if session else None,
    )


@router.post("/signout")
async def api_auth_signout() -> dict[str, str]:
    """Sign out the current user."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.auth.sign_out()
    return {"status": "signed_out"}


@router.get("/user")
async def api_auth_get_user(authorization: str | None = Header(None)) -> AuthResponse:
    """Get the current user from JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    jwt = authorization[7:]
    result = validate_access_token(jwt)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id, email = result
    return AuthResponse(user_id=user_id, email=email)


# ---------------------------------------------------------------------------
# Token provisioning — iOS sends Supabase session to local server after QR pair
# ---------------------------------------------------------------------------


@router.post("/provision")
async def api_auth_provision(body: ProvisionRequest) -> ProvisionResponse:
    """Provision this server with a user's Supabase session.

    Called by the iOS app after QR code pairing. Stores tokens in
    ~/.glyx/session (0600) so the local executor can subscribe to
    Supabase Realtime without a service role key.
    """
    result = validate_access_token(body.access_token)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid access token")

    user_id, email = result
    save_session(SessionTokens(access_token=body.access_token, refresh_token=body.refresh_token))

    # Wake up the executor if it was waiting for credentials
    from api.local_executor import notify_session_provisioned

    await notify_session_provisioned()

    return ProvisionResponse(status=ProvisionStatus.PROVISIONED, user_id=user_id, email=email)


@router.get("/provision/status")
async def api_auth_provision_status() -> ProvisionStatusResponse:
    """Check whether this server has been provisioned with user credentials."""
    tokens = load_session()
    if not tokens:
        return ProvisionStatusResponse(status=ProvisionStatus.UNPROVISIONED)

    result = validate_access_token(tokens.access_token)
    if result:
        user_id, email = result
        return ProvisionStatusResponse(
            status=ProvisionStatus.PROVISIONED,
            user_id=user_id,
            email=email,
            has_refresh_token=True,
        )

    # Access token expired but refresh token may still be good
    refreshed = refresh_session(tokens.refresh_token)
    if refreshed:
        result = validate_access_token(refreshed.access_token)
        if result:
            user_id, email = result
            return ProvisionStatusResponse(
                status=ProvisionStatus.PROVISIONED,
                user_id=user_id,
                email=email,
                has_refresh_token=True,
            )

    return ProvisionStatusResponse(status=ProvisionStatus.EXPIRED, has_refresh_token=True)


@router.post("/provision/revoke")
async def api_auth_provision_revoke() -> dict[str, str]:
    """Delete provisioned credentials from this server."""
    delete_session()
    return {"status": "revoked"}

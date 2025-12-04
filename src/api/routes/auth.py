"""Authentication API routes."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from api.utils import get_supabase
from glyx_python_sdk.types import AuthResponse, AuthSignInRequest, AuthSignUpRequest

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/signup")
async def api_auth_signup(body: AuthSignUpRequest) -> AuthResponse:
    """Sign up a new user via Supabase Auth."""
    client = get_supabase()
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
    client = get_supabase()
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
    client = get_supabase()
    client.auth.sign_out()
    return {"status": "signed_out"}


@router.get("/user")
async def api_auth_get_user(authorization: str | None = Header(None)) -> AuthResponse:
    """Get the current user from JWT token."""
    client = get_supabase()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    jwt = authorization[7:]
    response = client.auth.get_user(jwt)
    user = response.user
    return AuthResponse(
        user_id=user.id if user else None,
        email=user.email if user else None,
    )

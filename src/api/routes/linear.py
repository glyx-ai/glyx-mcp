"""Linear OAuth API routes."""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from supabase import create_client

from glyx_python_sdk.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/linear", tags=["Linear"])


class LinearEndpoints(StrEnum):
    """Linear API endpoints."""

    AUTHORIZE = "https://linear.app/oauth/authorize"
    TOKEN = "https://api.linear.app/oauth/token"
    GRAPHQL = "https://api.linear.app/graphql"


class LinearScope(StrEnum):
    """Linear OAuth scopes."""

    READ = "read"
    WRITE = "write"


class LinearGrantType(StrEnum):
    """Linear OAuth grant types."""

    AUTHORIZATION_CODE = "authorization_code"


@router.get("/authorize")
async def authorize(request: Request) -> RedirectResponse:
    """Redirect to Linear OAuth authorization page."""
    if not settings.linear_client_id:
        raise HTTPException(status_code=500, detail="Linear Client ID not configured")

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/linear/callback"

    params = {
        "client_id": settings.linear_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": f"{LinearScope.READ},{LinearScope.WRITE}",
        "state": "random_state_string",  # TODO: Generate and validate state for CSRF protection
    }

    url = f"{LinearEndpoints.AUTHORIZE}?{urlencode(params)}"
    return RedirectResponse(url)


@router.get("/callback")
async def callback(code: str, state: str, request: Request) -> dict[str, Any]:
    """Handle Linear OAuth callback."""
    if not settings.linear_client_id or not settings.linear_client_secret:
        raise HTTPException(status_code=500, detail="Linear credentials not configured")

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/linear/callback"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            LinearEndpoints.TOKEN,
            data={
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": settings.linear_client_id,
                "client_secret": settings.linear_client_secret,
                "grant_type": LinearGrantType.AUTHORIZATION_CODE,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            logger.error(f"Linear OAuth failed: {response.text}")
            raise HTTPException(status_code=400, detail="Failed to retrieve access token")

        token_data = response.json()
        access_token = token_data.get("access_token")

        if not access_token:
            raise HTTPException(status_code=400, detail="No access token in response")

        # Fetch user info
        user_response = await client.post(
            LinearEndpoints.GRAPHQL,
            json={"query": "query Me { viewer { id name email organization { id name } } }"},
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        )

        if user_response.status_code == 200:
            user_data = user_response.json().get("data", {}).get("viewer", {})
            await _store_linear_installation(user_data, access_token, token_data)

        return {"status": "success", "message": "Linear successfully connected", "data": token_data}


async def _store_linear_installation(user_data: dict, access_token: str, token_data: dict) -> None:
    """Store Linear installation data in Supabase."""
    linear_user_id = user_data.get("id")
    organization_id = user_data.get("organization", {}).get("id")

    if not linear_user_id:
        return

    supabase = create_client(settings.supabase_url, settings.supabase_anon_key)
    try:
        supabase.table("linear_installations").upsert(
            {
                "linear_user_id": linear_user_id,
                "organization_id": organization_id,
                "access_token": access_token,
                "token_data": token_data,
            }
        ).execute()
    except Exception as e:
        logger.error(f"Failed to save token to database: {e}")

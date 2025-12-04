"""Shared utilities for API routes."""

from __future__ import annotations

from glyx_python_sdk import settings
from supabase import create_client


def get_supabase():
    """Get Supabase client instance."""
    return create_client(settings.supabase_url, settings.supabase_anon_key)

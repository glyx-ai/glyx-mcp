#!/usr/bin/env python3
"""List users from Supabase auth to find user IDs for daemon registration."""

from __future__ import annotations

import os
import sys

from supabase import create_client


def main() -> int:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        # Try anon key - won't work for auth.users but might work for profiles
        key = os.environ.get("SUPABASE_ANON_KEY")
        if not url or not key:
            print("Error: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
            return 1

    client = create_client(url, key)

    # Try to get users from auth (requires service role key)
    try:
        users = client.auth.admin.list_users()
        if users:
            print("Users:")
            print("-" * 80)
            for user in users[:10]:  # Limit to first 10
                print(f"  ID:    {user.id}")
                print(f"  Email: {user.email}")
                print("-" * 80)
            return 0
    except Exception as e:
        print(f"Could not list users from auth: {e}", file=sys.stderr)

    # Try profiles table as fallback
    try:
        result = client.table("profiles").select("id, email, display_name").limit(10).execute()
        if result.data:
            print("Profiles:")
            print("-" * 80)
            for profile in result.data:
                print(f"  ID:    {profile['id']}")
                print(f"  Email: {profile.get('email', 'N/A')}")
                print(f"  Name:  {profile.get('display_name', 'N/A')}")
                print("-" * 80)
            return 0
    except Exception as e:
        print(f"Could not list profiles: {e}", file=sys.stderr)

    print("No users found. You may need SUPABASE_SERVICE_ROLE_KEY to access users.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

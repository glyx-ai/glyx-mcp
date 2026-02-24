#!/usr/bin/env python3
"""List paired devices from Supabase to help find device IDs for the MCP executor."""

from __future__ import annotations

import os
import sys

from supabase import create_client


def main() -> int:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY")

    if not url or not key:
        print("Error: Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY", file=sys.stderr)
        return 1

    client = create_client(url, key)

    result = client.table("paired_devices").select("id, name, hostname, status, paired_at").execute()

    if not result.data:
        print("No paired devices found.")
        return 0

    print("Paired Devices:")
    print("-" * 80)
    for device in result.data:
        print(f"  ID:       {device['id']}")
        print(f"  Name:     {device.get('name', 'N/A')}")
        print(f"  Hostname: {device.get('hostname', 'N/A')}")
        print(f"  Status:   {device.get('status', 'unknown')}")
        print(f"  Paired:   {device.get('paired_at', 'N/A')}")
        print("-" * 80)

    print(f"\nTo run executor: GLYX_DEVICE_ID=<id> uv run glyx-executor")
    return 0


if __name__ == "__main__":
    sys.exit(main())

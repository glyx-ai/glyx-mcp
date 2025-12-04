#!/usr/bin/env python3
"""
Minimal Supabase Realtime test:
- Subscribes to INSERT events on public.organizations
- Inserts a new row
- Verifies the realtime payload is received within a timeout
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict

from supabase import Client, create_client


DEFAULT_PROJECT_ID = "a0000000-0000-0000-0000-000000000001"
DEFAULT_TABLE = "organizations"
DEFAULT_SCHEMA = "public"
DEFAULT_TIMEOUT_SECONDS = 15


def get_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(2)
    return value


def create_supabase_client() -> Client:
    url = get_env("SUPABASE_URL")
    key = get_env("SUPABASE_ANON_KEY")
    return create_client(url, key)


def subscribe_to_inserts(
    client: Client,
    schema: str,
    table: str,
    on_payload: Callable[[Dict[str, Any]], None],
) -> Any:
    """
    Sure: subscribe to postgres INSERT changes for a given table.
    Returns the channel object.
    """
    channel = client.channel(f"realtime-{table}-inserts")
    # The supabase-py v2 API accepts a dict filter for postgres_changes
    channel.on(
        "postgres_changes",
        {"event": "INSERT", "schema": schema, "table": table},
        on_payload,
    )
    channel.subscribe()
    return channel


def insert_test_row(client: Client, table: str) -> dict[str, Any]:
    """
    Insert a test row into the organizations table matching the API's expected shape.
    """
    now = datetime.utcnow().isoformat()
    name = f"realtime-test-{int(time.time())}"
    data = {
        "project_id": DEFAULT_PROJECT_ID,
        "name": name,
        "description": f"Realtime test at {now}",
        "template": None,
        "config": {},
        "status": "draft",
        "stages": [],
    }
    resp = client.table(table).insert(data).execute()
    if not resp.data:
        raise RuntimeError("Insert returned no data")
    return resp.data[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Supabase Realtime on INSERT events.")
    parser.add_argument("--table", default=DEFAULT_TABLE, help="Table to watch for INSERTs (default: organizations)")
    parser.add_argument("--schema", default=DEFAULT_SCHEMA, help="Database schema (default: public)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Timeout in seconds (default: 15)")
    args = parser.parse_args()

    client = create_supabase_client()

    event = threading.Event()
    received_payload: dict[str, Any] | None = None

    def on_insert(payload: dict[str, Any]) -> None:
        nonlocal received_payload
        received_payload = payload
        event.set()

    subscribe_to_inserts(client, args.schema, args.table, on_insert)

    # small delay to ensure subscription is active
    time.sleep(1.0)

    try:
        inserted = insert_test_row(client, args.table)
    except Exception as e:
        print(f"Insert failed: {e}", file=sys.stderr)
        return 1

    if not event.wait(timeout=args.timeout):
        print(f"Did not receive realtime payload within {args.timeout}s", file=sys.stderr)
        return 1

    # Basic validation: the payload includes 'new' row with same name
    try:
        new_row = received_payload.get("new", {}) if received_payload else {}
        ok = new_row and new_row.get("name") == inserted.get("name")
    except Exception:
        ok = False

    if not ok:
        print("Received realtime payload, but contents did not match inserted row:", file=sys.stderr)
        print(json.dumps(received_payload or {}, indent=2))
        return 1

    print("✅ Supabase Realtime OK - received INSERT event for:", inserted.get("name"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

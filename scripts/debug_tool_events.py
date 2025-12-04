#!/usr/bin/env python3
"""Debug script to trace tool call events from cursor agent."""

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from glyx.core.agent import AgentKey, ComposableAgent
from glyx.mcp.models.cursor import (
    BaseCursorEvent,
    CursorToolCallEvent,
    parse_cursor_event,
)

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    agent = ComposableAgent.from_key(AgentKey.CURSOR)

    task = {
        "prompt": "Run 'echo hello world' in the shell",
        "model": "auto",
        "output_format": "stream-json",
    }

    print(f"Running agent with task: {task['prompt']}")
    print("Filtering for non-thinking events...\n")

    event_count = 0
    interesting_events = []

    async for event in agent.execute_stream(task, timeout=120):
        event_count += 1
        event_type = event.get("type", "unknown")

        if event_type == "agent_event":
            inner = event.get("event")
            if isinstance(inner, dict):
                inner_type = inner.get("type", "")

                # Skip thinking deltas (too noisy)
                if inner_type == "thinking":
                    continue

                interesting_events.append(inner)

                print(f"\n{'='*60}")
                print(f"EVENT #{len(interesting_events)} - Inner type: {inner_type}")
                print(f"{'='*60}")

                # Parse using typed cursor models
                raw = inner.get("raw", inner)
                parsed = parse_cursor_event(raw)
                print(f"Parsed type: {type(parsed).__name__}")

                # If it's a tool call, show the extracted info
                if isinstance(parsed, CursorToolCallEvent):
                    tool_name = parsed.get_tool_name()
                    preview = parsed.get_preview()
                    print(f"\n>>> CURSOR TOOL CALL:")
                    print(f"    Tool name: {tool_name!r}")
                    print(f"    Preview: {preview!r}")
                    print(f"    Subtype: {parsed.subtype}")
                    print(f"    Call ID: {parsed.call_id}")

        elif event_type in ("agent_complete", "agent_timeout", "agent_error"):
            print(f"\n{'='*60}")
            print(f"FINAL EVENT: {event_type}")
            print(f"{'='*60}")
            print(json.dumps(event, indent=2, default=str))

    print(f"\n\nTotal events: {event_count}, Interesting events: {len(interesting_events)}")


if __name__ == "__main__":
    asyncio.run(main())

"""Session management tools for retrieving conversation history."""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from fastmcp import Context

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

SESSION_DB = Path(os.environ.get("GLYX_SESSION_DB", "/tmp/glyx_sessions.db"))


async def list_sessions(ctx: Context) -> str:
    """List all conversation sessions with their metadata.

    Returns:
        JSON string with sessions array containing id, created_at, updated_at, message_count
    """
    try:
        if not SESSION_DB.exists():
            return '{"sessions": []}'

        conn = sqlite3.connect(str(SESSION_DB))
        cursor = conn.cursor()

        # Query to get all unique session IDs with metadata
        cursor.execute("""
            SELECT
                session_id,
                MIN(created_at) as created_at,
                MAX(created_at) as updated_at,
                COUNT(*) as message_count
            FROM items
            GROUP BY session_id
            ORDER BY MAX(created_at) DESC
        """)

        sessions = []
        for row in cursor.fetchall():
            sessions.append({
                "id": row[0],
                "created_at": row[1],
                "updated_at": row[2],
                "message_count": row[3]
            })

        conn.close()

        import json
        return json.dumps({"sessions": sessions})

    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        return f'{{"error": "{str(e)}"}}'


async def get_session_messages(
    ctx: Context,
    session_id: str,
    limit: int | None = None
) -> str:
    """Get messages for a specific conversation session.

    Args:
        session_id: The session/conversation ID
        limit: Optional limit on number of messages to return (most recent first)

    Returns:
        JSON string with messages array containing role, content, created_at
    """
    try:
        if not SESSION_DB.exists():
            return '{"messages": []}'

        conn = sqlite3.connect(str(SESSION_DB))
        cursor = conn.cursor()

        # Query to get messages for this session
        query = """
            SELECT role, content, created_at
            FROM items
            WHERE session_id = ?
            ORDER BY created_at ASC
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query, (session_id,))

        messages = []
        for row in cursor.fetchall():
            messages.append({
                "role": row[0],
                "content": row[1],
                "created_at": row[2]
            })

        conn.close()

        import json
        return json.dumps({"messages": messages})

    except Exception as e:
        logger.error(f"Failed to get session messages: {e}")
        return f'{{"error": "{str(e)}"}}'

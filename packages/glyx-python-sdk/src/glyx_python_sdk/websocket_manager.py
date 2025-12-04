from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


class RealtimeEvent(BaseModel):
    """Schema for realtime events sent over WebSocket."""

    type: str = Field(..., description="Event type identifier, e.g., 'agent.start'")
    data: dict[str, Any] = Field(default_factory=dict, description="Structured event payload")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO8601 UTC timestamp",
    )


class ConnectionManager:
    """Tracks active WebSocket connections and broadcasts events."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info(f"[WS] Client connected (active={len(self._connections)})")

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
        logger.info(f"[WS] Client disconnected (active={len(self._connections)})")

    async def broadcast_event(self, event: RealtimeEvent) -> None:
        """Broadcast a Pydantic event to all connected clients."""
        if not self._connections:
            return
        message_text = event.model_dump_json()
        await self._broadcast_text(message_text)

    async def broadcast(self, event_type: str, data: dict[str, Any]) -> None:
        """Helper to broadcast without constructing the model externally."""
        await self.broadcast_event(RealtimeEvent(type=event_type, data=data))

    async def _broadcast_text(self, text: str) -> None:
        stale: list[WebSocket] = []
        async with self._lock:
            targets = list(self._connections)
        for ws in targets:
            try:
                await ws.send_text(text)
            except Exception as e:
                logger.warning(f"[WS] Failed to send to a client: {e} (pruning)")
                stale.append(ws)
        if stale:
            async with self._lock:
                for ws in stale:
                    self._connections.discard(ws)
            logger.info(f"[WS] Pruned {len(stale)} stale connections (active={len(self._connections)})")


# Global singleton manager
manager = ConnectionManager()


async def broadcast_event(event_type: str, data: dict[str, Any]) -> None:
    """Public helper used by other modules to push events."""
    try:
        await manager.broadcast(event_type=event_type, data=data)
    except Exception as e:
        # Never raise from broadcast; log and continue
        logger.debug(f"[WS] Broadcast error (ignored): {e}")

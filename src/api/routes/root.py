"""Root route and static file serving."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/")
async def root():
    """Serve the repository deployment interface."""
    static_path = Path(__file__).parent.parent.parent / "static" / "index.html"
    if static_path.exists():
        return FileResponse(str(static_path))
    else:
        raise HTTPException(status_code=404, detail="UI not found")

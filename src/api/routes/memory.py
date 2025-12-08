"""Memory management API routes."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter
from openai import AsyncOpenAI

from glyx_python_sdk import save_memory, search_memory
from glyx_python_sdk.types import (
    MemoryInferRequest,
    MemoryInferResponse,
    MemorySuggestion,
    SaveMemoryRequest,
    SearchMemoryRequest,
)

router = APIRouter(prefix="/api/memory", tags=["Memory"])


@router.post("/save")
async def api_save_memory(body: SaveMemoryRequest) -> dict[str, str]:
    """Save memory via REST endpoint."""
    run_id = body.run_id or f"dashboard-{int(datetime.now().timestamp())}"
    result = save_memory(
        content=body.content,
        agent_id=body.agent_id,
        run_id=run_id,
        category=body.category,  # type: ignore
        directory_name=body.directory_name,
    )
    return {"status": "saved", "result": result}


@router.post("/search")
async def api_search_memory(body: SearchMemoryRequest) -> dict[str, list]:
    """Search memory via REST endpoint."""
    result = search_memory(
        query=body.query,
        category=body.category,  # type: ignore
        limit=body.limit,
    )
    memories = json.loads(result) if result else []
    return {"memories": memories}


@router.post(
    "/infer",
    summary="Infer Memories from Page Content",
    response_description="AI-suggested memories to save",
)
async def api_infer_memory(body: MemoryInferRequest) -> MemoryInferResponse:
    """
    Use AI to analyze page content and suggest relevant memories to save.

    This endpoint:
    1. Searches existing memories for context
    2. Uses GPT to analyze the page content
    3. Suggests relevant memories to save based on what's new/useful
    """
    client = AsyncOpenAI()

    # Search existing memories for context
    existing_context = ""
    if body.page_title:
        existing_result = search_memory(query=body.page_title, limit=5)
        existing_memories = json.loads(existing_result) if existing_result else []
        if existing_memories:
            existing_context = "\n".join(f"- {m.get('memory', '')}" for m in existing_memories[:5])

    system_prompt = """You are a knowledge extraction assistant. Analyze the provided page content and suggest 2-4 specific, actionable memories worth saving.

Focus on:
- Technical patterns, APIs, or code examples
- Architecture decisions or best practices
- Key concepts or definitions
- Useful commands or configurations

For each suggestion:
1. Extract the core information (be concise, 1-2 sentences)
2. Assign a category: architecture, integrations, code_style_guidelines, project_id, observability, product, key_concept, or tasks
3. Explain why this is worth remembering

Respond in JSON format:
{
  "analysis": "Brief summary of what the page is about",
  "suggestions": [
    {"content": "...", "category": "...", "reason": "..."}
  ]
}"""

    user_prompt = f"""Page: {body.page_title or "Unknown"}
URL: {body.page_url or "N/A"}
User context: {body.user_context or "None provided"}

Existing memories (avoid duplicating):
{existing_context or "None"}

Page content:
{body.page_content[:8000]}"""

    response = await client.chat.completions.create(
        model="gpt-5.1-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    result_text = response.choices[0].message.content or "{}"
    result_data = json.loads(result_text)

    suggestions = [MemorySuggestion(**s) for s in result_data.get("suggestions", [])]

    return MemoryInferResponse(
        suggestions=suggestions,
        analysis=result_data.get("analysis", "Unable to analyze content"),
    )

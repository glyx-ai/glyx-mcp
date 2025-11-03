"""Shot-scraper tool for browser screenshots and visual inspection."""

from __future__ import annotations

from fastmcp import Context
from pydantic import BaseModel, Field

from glyx_mcp.composable_agent import AgentKey, ComposableAgent


class ScreenshotConfig(BaseModel):
    """Configuration for shot-scraper screenshots."""
    url: str = Field(..., description="URL or local file path to capture")
    output: str | None = Field(None, description="Output file path")
    width: int = Field(1280, description="Viewport width in pixels")
    height: int | None = Field(None, description="Viewport height (None = full page)")
    selector: str | None = Field(None, description="CSS selector for specific element")
    wait: int | None = Field(None, description="Milliseconds to wait before screenshot")
    wait_for: str | None = Field(None, description="JavaScript condition to wait for")
    javascript: str | None = Field(None, description="JavaScript to execute before capture")
    retina: bool = Field(False, description="Use 2x scale factor")
    quality: int | None = Field(None, description="JPEG quality (1-100)")
    interactive: bool = Field(False, description="Open browser for manual interaction")
    log_console: bool = Field(False, description="Output console.log() to stderr")


async def use_shot_scraper(
    url: str,
    ctx: Context,
    output: str | None = None,
    width: int = 1280,
    height: int | None = None,
    selector: str | None = None,
    wait: int | None = None,
    wait_for: str | None = None,
    javascript: str | None = None,
    retina: bool = False,
    quality: int | None = None,
    interactive: bool = False,
    log_console: bool = False,
) -> str:
    """Take screenshots and perform visual inspection of web pages.

    Perfect for QA agents to verify designs, check layouts, and capture visual state.
    """
    config = ScreenshotConfig(
        url=url,
        output=output,
        width=width,
        height=height,
        selector=selector,
        wait=wait,
        wait_for=wait_for,
        javascript=javascript,
        retina=retina,
        quality=quality,
        interactive=interactive,
        log_console=log_console,
    )

    await ctx.info("shot-scraper starting", extra={"url": config.url})

    result = await ComposableAgent.from_key(AgentKey.SHOT_SCRAPER).execute(
        config.model_dump(exclude_none=True), timeout=120
    )

    await ctx.info("shot-scraper complete", extra={"exit_code": result.exit_code})

    return result.output if result.success else f"Screenshot failed:\n{result.output}"

# Visual Layer Feature

## Overview
Add visual inspection capabilities for Product/QA agents in the organization hierarchy.

## Goals
- Screenshot web pages and UI components
- Visual regression testing (compare baseline vs current)
- Enable QA agents to verify designs programmatically
- Support both local files and live URLs

## Architecture

### Phase 1: Screenshot Capability ✅
**Tool**: `shot-scraper` (Python CLI wrapping Playwright)
**Config**: `src/glyx_mcp/config/shot_scraper.json`
**Wrapper**: `src/glyx_mcp/tools/use_shot_scraper.py`

**Capabilities**:
- Full page screenshots
- Element-specific screenshots (CSS selectors)
- JavaScript execution before capture
- Wait for dynamic content
- Retina/high-DPI support

### Phase 2: Visual Diffing (TODO)
**Tool**: ImageMagick `compare` OR `pixelmatch-cli`
**Purpose**: Compare baseline vs current screenshots, highlight differences

**Flow**:
```
1. QA Agent takes screenshot of current state
2. Compares against baseline in repo
3. Generates diff image with highlighted changes
4. Reports pixel/percentage differences
```

### Phase 3: QA Orchestrator Agent (TODO)
**Purpose**: Coordinate visual testing workflows

**Example workflow**:
```
PM Agent: "Verify the login page matches design"
↓
QA Orchestrator:
  1. use_shot_scraper(url="http://localhost:3000/login")
  2. use_visual_diff(baseline="designs/login.png", current="screenshot.png")
  3. Analyze differences
  4. Report: "3 differences found: button color, spacing, font size"
```

## Installation Requirements

```bash
# shot-scraper
pip install shot-scraper
shot-scraper install  # Installs Playwright browsers

# ImageMagick (for visual diff)
# Ubuntu/Debian:
sudo apt-get install imagemagick

# macOS:
brew install imagemagick
```

## Testing Plan

### Unit Tests
- Config validation
- Pydantic model serialization
- Mock subprocess execution

### Integration Tests
```python
@pytest.mark.integration
async def test_shot_scraper_screenshot():
    agent = ComposableAgent.from_key(AgentKey.SHOT_SCRAPER)
    result = await agent.execute({
        "url": "https://example.com",
        "output": "/tmp/test.png"
    })
    assert result.success
    assert Path("/tmp/test.png").exists()
```

### E2E Tests (requires shot-scraper installed)
```python
@pytest.mark.e2e
async def test_visual_regression_workflow():
    # Full workflow: screenshot → diff → report
    pass
```

## Docker Strategy (Future)

For cross-platform support, wrap in Docker:
```json
{
  "shot_scraper_docker": {
    "command": "docker",
    "args": {
      "run": {"flag": "", "type": "string", "default": "run"},
      "rm": {"flag": "--rm", "type": "bool", "default": true},
      "volume": {"flag": "-v", "type": "string"},
      "image": {"flag": "", "type": "string", "default": "shot-scraper:latest"}
    }
  }
}
```

## Next Steps
1. ✅ Create shot_scraper.json config
2. ✅ Add SHOT_SCRAPER to AgentKey enum
3. ✅ Build use_shot_scraper.py wrapper
4. ✅ Register in server.py
5. ⏳ **CURRENT**: Verify shot-scraper is installed and works
6. TODO: Write integration tests
7. TODO: Add visual diff tool
8. TODO: Build QA orchestrator agent

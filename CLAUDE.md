# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

glyx-mcp is a FastMCP server that provides composable AI agent wrappers. Agents are defined via JSON configs and exposed as MCP tools.

## Essential Commands

```bash
# Install
uv pip install -e ".[dev]"

# Run MCP server
glyx-mcp

# Tests
uv run pytest                      # Alternative with uv

# Type checking & linting
mypy src/
ruff check src/

# Running Integration Tests
`uv run pytest tests/test_opencode_agent.py -m integration`
```

## Style Guidelines

- **Type checking**: Strict mypy mode enabled (`mypy.strict = true`)
- **Validation**: Use Pydantic models for all configs and structured data
- **Async**: All agent execution is async (`asyncio`)
- **Line length**: 120 characters (ruff)

## Architecture

### Core Pattern: ComposableAgent

Agents are JSON configs that map to CLI commands. The system transforms JSON → CLI args → subprocess execution → structured results.

**Flow**: `AgentConfig (JSON) → ComposableAgent.execute() → subprocess → AgentResult`

```python
# Agent configs: src/glyx_mcp/config/{agent}.json
{
  "agent_name": {
    "command": "cli-tool",
    "args": {
      "param": {"flag": "--flag", "type": "string", "required": true}
    }
  }
}

# Usage
agent = ComposableAgent.from_key(AgentKey.AIDER)
result: AgentResult = await agent.execute({"prompt": "...", "files": "..."})
```

### Key Components

- **composable_agent.py**: Core execution engine
  - `AgentConfig`: Pydantic model for JSON configs
  - `AgentResult`: Structured subprocess output (stdout, stderr, exit_code, timing)
  - `ComposableAgent.execute()`: Builds CLI command, runs subprocess, handles timeouts

- **config/*.json**: Agent definitions (aider, grok, claude, codex, etc.)
  - Validated on load via Pydantic
  - Support positional args (`flag: ""`), bool flags, defaults

- **tools/*.py**: MCP tool wrappers
  - Thin wrappers around `ComposableAgent.execute()`
  - Registered with FastMCP via `@mcp.tool()`

- **server.py**: FastMCP server entrypoint
  - Tool registration
  - Prompt registration (hardcoded: `agent_prompt`, `orchestrate_prompt`)

### Testing

Three test tiers with pytest markers:

1. **Unit tests** (no marker): Mocked subprocess, fast
2. **Integration tests** (`@pytest.mark.integration`): Mock CLIs, subprocess execution
3. **E2E tests** (`@pytest.mark.e2e`): Real CLIs + API keys required

Coverage threshold: 40% minimum (`pytest.ini`)

### Environment Variables

E2E tests require:
- `CLAUDE_API_KEY`
- `OPENROUTER_API_KEY`
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`

## Adding New Agents

1. Create config: `src/glyx_mcp/config/my_agent.json`
2. Add enum: `AgentKey.MY_AGENT` in `composable_agent.py`
3. Create tool: `src/glyx_mcp/tools/use_my_agent.py`
4. Register: `mcp.tool(use_my_agent)` in `server.py`
5. Test: Add to `tests/test_config_validation.py`

## Misc
```bash
# Run client integration tests (important)
uv run pytest tests/test_client_integration.py -vv -ss 
```
- To run logs, execute docker logs glyx-mcp-server
- Kill all Glyx MCP containers: docker rm -f $(docker ps -aq --filter "name=glyx-mcp")
- No defensive programming. Prefer a flat, expressive coding style.
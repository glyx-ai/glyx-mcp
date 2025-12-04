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
# Agent configs: agents/{agent}.json
{
  "agent_name": {
    "command": "cli-tool",
    "args": {
      "param": {"flag": "--flag", "type": "string", "required": true}
    }
  }
}

# Usage
agent = ComposableAgent.from_key(AgentKey.AIDER)  # from glyx.core.agent
result: AgentResult = await agent.execute({"prompt": "...", "files": "..."})
```

### Key Components

- **core/agent.py**: Core execution engine (`src/glyx/core/agent.py`)
  - `AgentConfig`: Pydantic model for JSON configs
  - `AgentResult`: Structured subprocess output (stdout, stderr, exit_code, timing)
  - `ComposableAgent.execute()`: Builds CLI command, runs subprocess, handles timeouts

- **agents/*.json**: Agent definitions (aider, grok, claude, codex, etc.)
  - Validated on load via Pydantic
  - Support positional args (`flag: ""`), bool flags, defaults

- **core/registry.py**: Auto-discovers JSON agent configs and registers MCP tools
  - No manual per-agent wrappers needed; tools are generated dynamically

- **mcp/server.py**: FastMCP server entrypoint (`src/glyx/mcp/server.py`)
  - Tool registration
  - Orchestrator tool (`orchestrate`) registration
  - Optional REST API endpoints (health, memory, features, agents)

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

1. Create config: `agents/my_agent.json`
2. Add enum (optional, for convenience): `AgentKey.MY_AGENT` in `src/glyx/core/agent.py`
3. No wrapper needed: agents are auto-discovered via `discover_and_register_agents(...)`
4. Run server: `glyx-mcp` (the tool `use_my_agent` will be available automatically)
5. Test: Add to `tests/test_config_validation.py`

## MCP Integration

### Claude Code/.mcp.json

```jsonc
{
  "mcpServers": {
    "glyx-mcp": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/telsiz/work/glyx-mcp",
        "fastmcp",
        "run",
        "src/glyx/mcp/server.py"
      ],
      "env": {
        "XAI_API_KEY": "...",
        "OPENAI_API_KEY": "...",
        "OPENROUTER_API_KEY": "...",
        "DEFAULT_MODEL": "auto"
      }
    }
  }
}
```

### Cursor Integration

The `use_cursor` MCP tool deploys Cursor cloud agents for autonomous coding via the cursor-agent CLI.

## Misc
```bash
# Run client integration tests (important)
uv run pytest tests/test_client_integration.py -vv -ss
```
- No defensive programming. Prefer a flat, expressive coding style.
- Style guidelines: we ALWAYS put Python imports at the top of the file.
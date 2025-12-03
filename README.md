# glyx-mcp

Composable AI agent framework with a FastMCP server, exposing multiple agent tools (Aider, Grok, etc.) through the MCP protocol. Agents are driven by JSON configs and executed as subprocesses for reliability and observability.

## Highlights

- **Composable by config**: Add agents via JSON, no code changes
- **Multiple entrypoints**: `glyx-mcp` (stdio), `glyx-mcp-http` (HTTP + WebSocket)
- **First-class tools**: Aider for code edits, Grok via OpenRouter, memory/session utilities
- **Tracing-ready**: Optional Langfuse instrumentation
- **Typed + tested**: Strict mypy, ruff, pytest

---

## Quickstart

### Option A — Docker (recommended)

```bash
# Build and run
docker compose build
# With .env (see .env.example for keys)
docker compose up
```

This starts the MCP server (`glyx-mcp`) inside a container. The compose file mounts your project directory into `/workspace` so file-editing agents (e.g., Aider) can modify your local files.

MCP client example (Claude Desktop `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "glyx-mcp": {
      "command": "docker",
      "args": ["compose", "run", "--rm", "glyx-mcp"],
      "env": {
        "OPENROUTER_API_KEY": "your_key"
      }
    }
  }
}
```

### Option B — Native install

```bash
# Install uv (if needed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install package + dev deps
uv pip install -e ".[dev]"

# Run MCP server (stdio)
glyx-mcp

# Or run HTTP transport (HTTP + WS)
glyx-mcp-http
```

> Tip: `./install.sh` installs tools like Aider/OpenCode for you if you prefer a one-shot setup.

---

## Environment

Copy `.env.example` to `.env` and fill as needed. Supported variables (see `src/glyx/mcp/settings.py`):

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `OPENROUTER_API_KEY`
- `CLAUDE_API_KEY`
- `MEM0_API_KEY`
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` (optional tracing)
- `DEFAULT_ORCHESTRATOR_MODEL` (default: `gpt-5`)
- `DEFAULT_AIDER_MODEL` (default: `gpt-5`)
- `DEFAULT_GROK_MODEL` (default: `openrouter/x-ai/grok-4-fast`)

When running via Docker Compose, `.env` is loaded automatically.

---

## Running modes

- **Stdio (default)**: `glyx-mcp` — best for Claude Code / CLI MCP clients
- **HTTP**: `glyx-mcp-http` — serves MCP over HTTP with realtime WebSocket events

Entrypoints are defined in `pyproject.toml`:

```toml
[project.scripts]
glyx-mcp = "glyx.mcp.server:main"
glyx-mcp-http = "glyx.mcp.server:main_http"
```

---

## Tools overview

- **Aider** (`use_aider`) — AI code editing across specified files
- **Grok** (`use_grok`) — general reasoning via OpenRouter/xAI (OpenCode CLI)
- **Memory** (`save_memory`, `search_memory`) — lightweight vector memory via `mem0`
- **Sessions** (`list_sessions`, `get_session_messages`) — conversation history helpers
- **Orchestrate** (`orchestrate`) — coordinates multiple agents for complex tasks

See implementations under `src/glyx/mcp/tools/`.

---

## Adding an agent

Agents are defined by JSON configs and auto-registered at startup:

1) Drop a config file into `agents/` (e.g., `grok.json`).
2) The server discovers configs and registers an MCP tool per agent.

Config → CLI execution is handled by `ComposableAgent` (`src/glyx/mcp/composable_agent.py`): it maps config args to CLI flags, spawns a subprocess, and returns structured output with timing and exit code. Discovery is performed in `src/glyx/core/registry.py` and wired from `src/glyx/mcp/server.py`.

Minimal example config shape:

```json
{
  "my_agent": {
    "command": "cli-tool",
    "args": {
      "prompt": { "flag": "--prompt", "type": "string", "required": true },
      "files":  { "flag": "--files",  "type": "string" },
      "model":  { "flag": "--model",  "type": "string", "default": "gpt-5" }
    },
    "description": "My agent",
    "capabilities": ["edit", "explain"]
  }
}
```

---

## Tracing (optional)

If `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` are provided, Langfuse tracing is enabled automatically with request/response metadata and timing. Without keys, tracing is disabled with zero overhead.

---

## Development

```bash
# Install dev deps
uv pip install -e ".[dev]"

# Type check / lint
mypy src/
ruff check src/

# Run tests (unit by default)
uv run pytest -q

# Integration / E2E markers
uv run pytest -m integration
uv run pytest -m e2e

# Client integration (useful locally)
uv run pytest tests/test_client_integration.py -vv -ss
```

- Python ≥ 3.11
- Strict mypy, ruff line length 120
- Coverage threshold is 40% (`pytest.ini`)

---

## MCP client configuration examples

Native (stdio):

```json
{
  "mcpServers": {
    "glyx-mcp": { "command": "glyx-mcp" }
  }
}
```

HTTP:

```json
{
  "mcpServers": {
    "glyx-mcp": {
      "command": "bash",
      "args": ["-lc", "glyx-mcp-http"],
      "transport": {
        "type": "http",
        "url": "http://localhost:8000"
      }
    }
  }
}
```

---

## Deployments

| Service | Platform | URL |
|---------|----------|-----|
| MCP Server | Fly.io | `https://glyx-mcp.fly.dev` |
| UI | Vercel | `https://glyx.vercel.app` |

### Deploy to Fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Deploy (uses Dockerfile)
fly deploy
```

### MCP Client Configuration (Fly.io)

```json
{
  "mcpServers": {
    "glyx-mcp": {
      "transport": {
        "type": "http",
        "url": "https://glyx-mcp.fly.dev/mcp"
      }
    }
  }
}
```

### Environment Variables (Fly.io)

Set secrets via `fly secrets set`:

```bash
fly secrets set OPENAI_API_KEY=sk-...
fly secrets set ANTHROPIC_API_KEY=sk-ant-...
fly secrets set OPENROUTER_API_KEY=sk-or-...
```

---

## Contributing

PRs welcome. Please follow the style guidelines above and keep code clear, typed, and well-factored. Run mypy, ruff, and tests before submitting.

## License

MIT

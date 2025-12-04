# Quick Start Guide

Get glyx-mcp running in 5 minutes.

## Option 1: Docker (Fastest)

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Edit .env and add your API keys
# Required: OPENAI_API_KEY, ANTHROPIC_API_KEY, OPENROUTER_API_KEY

# 3. Build and run
docker compose up -d

# 4. Check health
curl http://localhost:8080/api/healthz

# 5. View logs
docker compose logs -f
```

**MCP Client Config** (Claude Desktop, etc.):
```json
{
  "mcpServers": {
    "glyx-mcp": {
      "transport": {
        "type": "http",
        "url": "http://localhost:8080/mcp"
      }
    }
  }
}
```

---

## Option 2: Native Install

```bash
# 1. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install package
uv pip install -e ".[dev]"

# 3. (Optional) Install agent CLIs
./install.sh

# 4. Set API keys
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export OPENROUTER_API_KEY=sk-or-...

# 5. Run server
glyx-mcp-http
```

**MCP Client Config:**
```json
{
  "mcpServers": {
    "glyx-mcp": {
      "command": "glyx-mcp",
      "env": {
        "OPENAI_API_KEY": "sk-...",
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "OPENROUTER_API_KEY": "sk-or-..."
      }
    }
  }
}
```

---

## Option 3: Production (Fly.io)

```bash
# 1. Install flyctl
curl -L https://fly.io/install.sh | sh

# 2. Login
fly auth login

# 3. Configure environment
cp .env.production .env.production.local
# Edit and add your API keys

# 4. Deploy
./deploy.sh

# 5. Verify
curl https://glyx-mcp.fly.dev/api/healthz
```

**MCP Client Config:**
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

---

## Available Tools

Once running, you'll have access to these MCP tools:

- `use_aider` - AI code editing
- `use_grok` - Fast reasoning via Grok
- `use_claude` - Claude analysis
- `use_opencode` - General OpenCode CLI
- `use_cursor` - Cursor agent deployment
- `orchestrate` - Multi-agent orchestration
- `save_memory` / `search_memory` - Vector memory
- `create_agent` / `list_agents` - Agent management

---

## API Endpoints

- `GET /api/healthz` - Health check
- `GET /api/health/detailed` - Detailed status
- `GET /api/metrics` - Performance metrics
- `GET /api/agents` - List available agents
- `POST /api/tasks` - Create tasks
- `POST /stream/cursor` - Stream agent execution

---

## Troubleshooting

**Server won't start:**
```bash
# Check if port is in use
lsof -i :8080

# Try different port
PORT=8081 glyx-mcp-http
```

**Agent not found:**
```bash
# List available agents
curl http://localhost:8080/api/agents

# Check agent configs
ls agents/*.json
```

**Health check fails:**
```bash
# View detailed status
curl http://localhost:8080/api/health/detailed

# Check logs
docker compose logs glyx-mcp  # Docker
# or
tail -f logs/*.log  # Native
```

---

## Next Steps

- Read [DEPLOYMENT.md](docs/DEPLOYMENT.md) for production setup
- Read [AGENTS.md](AGENTS.md) for development guidelines
- Check [README.md](README.md) for full documentation

---

**Need help?** Open an issue on GitHub or check the docs folder.

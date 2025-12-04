# Repository Refactoring Status: glyx-mcp → glyx-ai

## Goal

Reorganize repository into cleaner structure:
- `src/python-sdk/` - SDK package
- `src/mcp/` - MCP protocol (tools, prompts, resources)
- `src/api/` - REST API endpoints
- Combined server orchestrates both on same port

## Completed ✅

1. ✅ SDK moved from `packages/sdk/` to `src/python-sdk/`
2. ✅ MCP structure created:
   - `src/mcp/server.py` - MCP server setup
   - `src/mcp/tools/` - MCP tools moved
   - `src/mcp/webhooks/` - Webhooks moved
   - `src/mcp/integrations/` - Integrations moved
3. ✅ API structure created:
   - `src/api/server.py` - Combined server
   - `src/api/routes/health.py` - Health endpoints extracted
   - `src/api/utils.py` - Shared utilities
4. ✅ `pyproject.toml` updated:
   - Scripts point to new locations
   - SDK path updated to `src/python-sdk`

## In Progress 🔄

1. 🔄 Extracting remaining API routes (39 routes from old server.py)
2. 🔄 Fixing imports throughout codebase
3. 🔄 Updating configuration files

## Remaining ⏳

1. ⏳ Extract remaining API routes:
   - Agent sequences (5 routes)
   - Agent workflows (5 routes)
   - Organizations (4 routes)
   - Tasks (7 routes)
   - Auth (4 routes)
   - Memory (3 routes)
   - Agents (1 route)
   - Streaming (2 routes)
   - Deployments (4 routes)
   - Webhooks (GitHub, Linear)

2. ⏳ Fix all imports:
   - Update `from glyx.mcp.*` to `from mcp.*`
   - Update test imports
   - Update script imports

3. ⏳ Update configuration:
   - Dockerfile paths
   - compose.yml paths
   - Documentation references
   - Script references

4. ⏳ Clean up:
   - Remove old `src/glyx/` directory
   - Remove old `packages/sdk/` directory
   - Update all documentation

## New Structure

```
src/
├── python-sdk/          # SDK package (from packages/sdk/)
│   ├── agents/         # Agent JSON configs
│   └── glyx_python_sdk/  # SDK source
├── mcp/                # MCP protocol
│   ├── tools/          # MCP tools
│   ├── webhooks/       # Webhook handlers
│   └── integrations/   # External integrations
└── api/                # REST API
    ├── routes/         # API route handlers
    └── server.py       # Combined server (MCP + API)
```

## Entry Points

- `mcp.server:main` - Stdio MCP server
- `api.server:run_http` - Combined HTTP server (MCP + REST API)

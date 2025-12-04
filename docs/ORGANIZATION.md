# Repository Organization

This document outlines the repository structure and organization principles.

## Current Structure

```
glyx-ai/
├── README.md              # Main project documentation
├── QUICKSTART.md          # Quick start guide
├── AGENTS.md              # Agent development guide
├── CLAUDE.md              # Claude-specific guidance
├── pyproject.toml         # Python project configuration
├── compose.yml            # Docker Compose configuration
├── Dockerfile             # Docker image definition
├── fly.toml               # Fly.io deployment config
│
├── docs/                  # Documentation
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   └── examples/          # Example configurations
│       └── docker-mcp-catalog.yaml
│
├── packages/              # Monorepo packages
│   └── sdk/               # Core SDK package
│       ├── agents/        # Agent JSON configurations
│       └── glyx_python_sdk/  # SDK source code
│
├── src/                   # Source code
│   └── glyx/              # Main application package
│       ├── mcp/          # FastMCP server
│       └── tasks/        # Task management
│
├── scripts/               # Utility scripts
├── tests/                 # Test suite
└── supabase/             # Database migrations
```

## Files Removed

The following files were removed as they were unnecessary or personal configs:

- **`opencode.jsonc`** - OpenCode client configuration (not part of this project)
- **`package-lock.json`** - Empty npm lockfile (Python project, not needed)
- **`.sessions.db`** - SQLite database file (now gitignored)

## Files Reorganized

- **`docker-mcp-catalog.yaml`** → moved to `docs/examples/` for better organization

## Organization Principles

### Root Directory
- Keep only essential files at root: README, QUICKSTART, config files (pyproject.toml, compose.yml, etc.)
- Documentation guides stay at root for visibility (AGENTS.md, CLAUDE.md)
- All detailed docs go in `docs/`

### Documentation
- **Root level**: Quick references and getting started guides
- **`docs/`**: Detailed documentation, architecture, deployment guides
- **`docs/examples/`**: Example configurations and usage patterns

### Configuration
- Agent configs: `packages/sdk/agents/*.json` (moved into SDK)
- Docker configs: Root level (compose.yml, Dockerfile)
- Deployment configs: Root level (fly.toml)

### Source Code
- Main application: `src/glyx/` (standard Python src layout)
- SDK package: `packages/sdk/` (simplified from `packages/glyx-python-sdk/`)
- Tests: `tests/`

## Gitignore Coverage

All generated files are properly gitignored:
- `__pycache__/` - Python bytecode
- `*.sqlite`, `*.sqlite3`, `*.db` - Database files
- `.ruff_cache/` - Ruff linter cache
- `.mypy_cache/` - MyPy type checker cache
- `htmlcov/` - Coverage reports
- `.venv/`, `venv/` - Virtual environments

## Future Organization Improvements

Potential improvements for better organization:

1. **Config Directory**: Consider creating `config/` for example configurations
2. **Documentation Consolidation**: Some markdown files at root could be moved to `docs/` if they become less frequently accessed
3. **Examples**: Create `examples/` directory for usage examples and sample configurations

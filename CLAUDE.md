# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

glyx-mcp is a FastMCP server built on **glyx-python-sdk** that provides composable AI agent wrappers, REST APIs, webhooks, and real-time communication for the Glyx ecosystem.

**Key Components:**
- **FastMCP Server**: MCP protocol for Claude Code integration (stdio transport)
- **FastAPI REST API**: HTTP endpoints for web/mobile clients
- **WebSocket**: Real-time event broadcasting
- **Knock Integration**: Push notifications to iOS app
- **Device Dispatch**: iOS app → Mac daemon task execution

## Project Structure

```
/Users/hkt/projects/glyx-mcp/
├── src/
│   ├── glyx_mcp/                 # MCP server entry point
│   │   └── server.py             # FastMCP server setup & tool registration
│   ├── api/                       # REST API + Webhooks
│   │   ├── server.py             # Combined FastAPI app (MCP + REST)
│   │   ├── models/               # Pydantic models
│   │   │   ├── notifications.py  # TaskNotificationPayload, GitHubNotificationPayload
│   │   │   └── linear.py         # Linear webhook models
│   │   ├── routes/               # API endpoints
│   │   │   ├── agents.py         # Agent listing & import (306 lines)
│   │   │   ├── tasks.py          # Task management & smart tasks (246 lines)
│   │   │   ├── streaming.py      # SSE/WebSocket streaming (142 lines)
│   │   │   ├── health.py         # Health checks & monitoring (166 lines)
│   │   │   ├── pair.py           # Device pairing script (266 lines)
│   │   │   ├── organizations.py  # Org management (62 lines)
│   │   │   ├── auth.py           # Authentication (67 lines)
│   │   │   ├── github.py         # GitHub integration (141 lines)
│   │   │   ├── linear.py         # Linear integration (129 lines)
│   │   │   ├── memory.py         # Memory/semantic search (122 lines)
│   │   │   ├── workflows.py      # Workflow execution (133 lines)
│   │   │   ├── composable_workflows.py  # Composable API agents (102 lines)
│   │   │   ├── sequences.py      # Agent sequences/pipelines (89 lines)
│   │   │   ├── deployments.py    # Deployment management (88 lines)
│   │   │   └── root.py           # Root endpoint (20 lines)
│   │   ├── webhooks/
│   │   │   ├── github.py         # GitHub webhook handler with notifications
│   │   │   ├── linear.py         # Linear webhook handler with notifications
│   │   │   └── base.py           # Webhook base classes
│   │   └── integrations/
│   │       ├── github.py         # GitHub GraphQL client
│   │       ├── linear.py         # Linear GraphQL client
│   │       └── claude_code.py    # Claude Code integration
│   ├── framework/
│   │   ├── cli.py                # CLI interface
│   │   └── lifecycle.py          # Feature lifecycle management with notifications
│   ├── integration_agents/
│   │   └── linear_agent.py       # Linear integration agent
│   └── python-sdk/
│       └── src/glyx_python_sdk/
│           ├── __init__.py       # SDK exports
│           ├── agent_types.py    # AgentConfig, AgentKey, AgentResult
│           ├── types.py          # Pydantic models (TaskData, StreamCursorRequest)
│           ├── composable_agents.py  # JSON-driven CLI agent wrapper
│           ├── orchestrator.py   # GlyxOrchestrator with streaming
│           ├── registry.py       # Agent discovery & registration
│           ├── pipelines.py      # Pipeline orchestration
│           ├── settings.py       # Configuration (Settings dataclass)
│           ├── memory.py         # Memory management with Mem0
│           ├── workflows.py      # Workflow management
│           ├── composable_workflows.py  # Composable workflows
│           ├── prompts.py        # Prompt templates
│           ├── websocket_manager.py  # WebSocket event broadcasting
│           ├── tools/
│           │   ├── device_dispatch.py  # iOS device task dispatch
│           │   ├── orchestrate.py      # Orchestration tool
│           │   ├── session_tools.py    # Session management
│           │   └── interact_with_user.py
│           ├── agents/
│           │   ├── glyx_sdk_agent.py       # SDK-powered agent
│           │   ├── documentation_agent.py  # Documentation retrieval
│           │   ├── cursor_agent.py
│           │   └── workflow_agent.py
│           ├── configs/          # JSON agent configurations
│           │   ├── cursor.json    # Cursor Cloud Agent
│           │   ├── grok.json      # Grok reasoning
│           │   ├── aider.json
│           │   ├── opencode.json
│           │   ├── claude.json
│           │   ├── codex.json
│           │   ├── gemini.json
│           │   ├── deepseek_r1.json
│           │   └── kimi_k2.json
│           ├── models/
│           │   ├── cursor.py      # Cursor event models
│           │   ├── response.py    # Response event models
│           │   ├── stream_items.py # Stream item types
│           │   └── task.py
│           └── integrations/
│               ├── linear.py      # Linear integration
│               └── github.py      # GitHub integration
├── supabase/
│   └── migrations/               # Database migrations
├── tests/
│   ├── test_notifications.py      # Knock notification tests
│   ├── test_framework.py
│   ├── test_github_integration.py
│   ├── test_linear_webhook.py
│   └── fixtures/
├── docs/                          # Architecture & deployment docs
├── infra/                         # Terraform deployment
├── scripts/
├── .env.example                   # Environment variables template
├── .env                           # Actual environment (with secrets)
├── pyproject.toml                 # Project dependencies & config
├── compose.yml                    # Docker Compose for local dev
└── Dockerfile                     # Multi-stage Docker build
```

## Essential Commands

```bash
# Install
uv pip install -e ".[dev]"

# Run MCP server (stdio mode for Claude Code)
glyx-mcp

# Run HTTP server (REST API + WebSocket)
glyx-mcp-http

# Tests
uv run pytest
uv run pytest tests/test_notifications.py -v
uv run pytest tests/test_client_integration.py -vv -ss

# Type checking & linting
mypy src/
ruff check src/
```

## Entry Points

### Stdio Mode (Claude Code MCP)
- **File**: `src/glyx_mcp/server.py`
- **Command**: `glyx-mcp`
- **Flow**: Creates FastMCP("glyx-ai"), registers tools, runs stdio transport

### HTTP Mode (REST API + WebSocket)
- **File**: `src/api/server.py`
- **Command**: `glyx-mcp-http`
- **Port**: 8080 (configurable via `PORT` env)
- **Endpoints**: MCP at `/mcp`, REST at `/api/*`

## API Endpoints

| Route | Method | Description |
|-------|--------|-------------|
| `/api/healthz` | GET | Basic health check |
| `/api/health/detailed` | GET | Detailed health with service checks |
| `/api/agents` | GET | List all available agents |
| `/api/agents` | POST | Create new agent from config |
| `/api/agents/import-from-url` | POST | Create agent from URL documentation |
| `/api/agents/import-stream` | POST | Stream agent creation with SSE |
| `/api/tasks` | GET/POST | Task CRUD |
| `/api/tasks/{task_id}` | GET/PATCH/DELETE | Task management |
| `/api/tasks/smart` | POST | AI-generated smart tasks |
| `/stream/cursor` | POST | Stream orchestrator execution (SSE) |
| `/ws` | WebSocket | Real-time updates |
| `/api/memory/save` | POST | Save semantic memory |
| `/api/memory/search` | POST | Search memory |
| `/api/workflows` | GET/POST | Workflow management |
| `/api/github/repos` | GET | List GitHub repos |
| `/api/github/prs` | GET | List pull requests |
| `/api/linear/issues` | GET | List Linear issues |
| `/pair` | GET | Device pairing script for iOS |

## Database Schema (Supabase)

### agent_tasks
Task dispatch to paired devices (iOS → Mac daemon)
- `id` (UUID), `user_id`, `device_id`, `agent_type`, `task_type`
- `payload` (JSONB), `status` (pending/running/completed/failed)
- `created_at`, `updated_at`

### paired_devices
User's paired iOS/Mac devices
- `id`, `user_id`, `name`, `relay_url`, `status` (online/offline)
- `hostname`, `os`, `paired_at`

### agent_sequences
Pipeline execution instances
- `id`, `project_id`, `name`, `description`
- `status` (in_progress/review/testing/done)
- `stages` (JSONB), `artifacts` (JSONB), `events` (JSONB)

### events
Activity feed/event log
- `orchestration_id`, `type`, `actor`, `content`, `metadata`

### tasks
Task management
- `id`, `title`, `description`, `status`
- `orchestration_id`, `linear_session_id`

## Agent System

### Available Agents (JSON configs in `configs/`)
- `cursor.json` - Cursor Cloud Agent (autonomous coding)
- `grok.json` - Grok (reasoning via OpenRouter)
- `aider.json` - Aider (code editing)
- `opencode.json` - OpenCode (general-purpose)
- `claude.json` - Claude (advanced reasoning)
- `codex.json` - Codex (code generation)
- `gemini.json` - Gemini (multimodal)
- `deepseek_r1.json` - DeepSeek R1 (reasoning)
- `kimi_k2.json` - Kimi K2 (extended thinking)

### Agent Execution Flow
```
AgentConfig (JSON) → ComposableAgent.from_key() → execute() → subprocess → AgentResult
```

### AgentResult Dataclass
```python
@dataclass
class AgentResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    execution_time: float = 0.0

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out
```

### Real-time Updates (3 mechanisms)
```python
broadcast_event()     # WebSocket → Web UI, Browser Extension
execute_stream()      # SSE → /stream/cursor endpoint
ctx.info()           # FastMCP → Claude Code
```

## Knock Notification Integration

### Configuration
- `KNOCK_API_KEY` - Required for server-side notifications
- `KNOCK_PUBLISHABLE_KEY` - For client-side (iOS app)

### Workflow Triggers
| Workflow Key | Recipients | Triggered By |
|---|---|---|
| `github-activity` | `["github-channel"]` | GitHub webhooks |
| `task-created` | `[assignee_id]` | Task creation API |
| `feature-lifecycle` | `["feature-channel"]` | Feature start |
| `agent-start` | `[user_id]` | Agent started (for iOS) |
| `agent-needs-input` | `[user_id]` | HITL required |
| `agent-completed` | `[user_id]` | Agent finished |
| `agent-error` | `[user_id]` | Agent error |

### Notification Trigger Locations
- `src/api/webhooks/github.py` (lines 62-67) - GitHub events
- `src/api/routes/tasks.py` (lines 96-99) - Task creation
- `src/framework/lifecycle.py` (lines 56-60) - Feature lifecycle

### iOS Integration (glyx-ios)
- iOS registers APNs token directly with Knock SDK
- Knock stores device tokens per user
- Server triggers workflow → Knock → APNs → iOS notification
- Deep linking via `session_id` in notification payload

## Device Dispatch (iOS → Mac)

### MCP Tools for Device Control
```python
dispatch_task(device_id, agent_type, prompt, cwd, user_id)  # Run agent task
run_on_device(device_id, command, cwd, user_id)            # Shell command
start_agent(device_id, agent_type, cwd, user_id)           # Start daemon
stop_agent(device_id, agent_type, user_id)                 # Stop daemon
list_devices(user_id)                                       # List paired devices
get_device_status(device_id, user_id)                      # Device status
get_task_status(task_id, user_id)                          # Poll task result
```

### Flow
1. iOS app calls MCP tool with device_id
2. Tool inserts into `agent_tasks` table
3. Supabase Realtime notifies daemon on Mac
4. Daemon executes task
5. Results stored in `agent_tasks.result`
6. iOS polls `get_task_status()` for result

## Session Management

### SQLite Session Storage
- Location: `/tmp/glyx_sessions.db` (or `GLYX_SESSION_DB` env)
- Table: `items` with `session_id`, `role`, `content`, `created_at`

### Session Tools
```python
list_sessions(ctx)                    # All sessions with metadata
get_session_messages(ctx, session_id) # Messages for session
```

## WebSocket Manager

**File**: `src/python-sdk/src/glyx_python_sdk/websocket_manager.py`

```python
manager = ConnectionManager()
broadcast_event("agent.start", {"agent": "claude", "task": "..."})
```

### Event Types
- `agent.start` / `agent.finish` - Lifecycle
- `tool_call` / `tool_output` - Tool execution
- `message` - Agent output
- `thinking` - Reasoning steps
- `error` - Exceptions

## Environment Variables

### API Keys
```
OPENAI_API_KEY              # OpenAI
ANTHROPIC_API_KEY           # Claude
OPENROUTER_API_KEY          # Grok, Deepseek, etc.
MEM0_API_KEY                # Memory storage
```

### Notifications
```
KNOCK_API_KEY               # Knock server-side
KNOCK_PUBLISHABLE_KEY       # Knock client-side
```

### Supabase
```
SUPABASE_URL                # https://xxx.supabase.co
SUPABASE_ANON_KEY           # Public key
SUPABASE_SERVICE_ROLE_KEY   # Admin key
```

### GitHub App
```
GITHUB_APP_ID
GITHUB_APP_PRIVATE_KEY
GITHUB_APP_CLIENT_ID
GITHUB_APP_CLIENT_SECRET
GITHUB_WEBHOOK_SECRET
GITHUB_APP_SLUG             # default: julian-e-acc
```

### Linear App
```
LINEAR_API_KEY
LINEAR_CLIENT_ID
LINEAR_CLIENT_SECRET
LINEAR_WEBHOOK_SECRET
```

### Auth / JWT
```
JWT_SECRET_KEY              # default: change-me-in-prod
JWT_ALGORITHM               # default: HS256
ACCESS_TOKEN_EXPIRES_MINUTES  # default: 15
```

### Model Defaults
```
DEFAULT_ORCHESTRATOR_MODEL  # default: gpt-5
DEFAULT_AIDER_MODEL         # default: gpt-5
DEFAULT_GROK_MODEL          # default: openrouter/x-ai/grok-4-fast
```

### Server
```
PORT                        # default: 8080
ENVIRONMENT                 # development | production
```

## Deployment

### Docker
```bash
docker compose up           # Local dev
docker build -t glyx-mcp .  # Production build
```

### Fly.io
```bash
./deploy.sh                 # Deploy to Fly.io
# Endpoint: https://glyx-mcp.fly.dev/
```

### Health Checks
```bash
curl https://glyx-mcp.fly.dev/api/healthz
curl https://glyx-mcp.fly.dev/api/health/detailed
```

## Related Projects

### glyx-ios (`/Users/hkt/projects/glyx-ios`)
- iOS mobile DevOps command center
- Bundle ID: `ai.glyx.app`
- Uses Knock SDK for push notifications
- Key files:
  - `Glyx/App/AppDelegate.swift` - APNs token handling
  - `Glyx/App/NotificationDelegate.swift` - Notification handling
  - `Glyx/Core/Services/NotificationService.swift` - Knock integration
  - `Glyx/App/GlyxApp.swift` - App entry point

### Knock Dashboard
- Push channel ID: `904dee2e-4b0f-4b31-a198-967b5e1a9d90`
- Workflows: agent-start, agent-needs-input, agent-completed, agent-error

## Style Guidelines

- **Type checking**: Strict mypy mode (`mypy.strict = true`)
- **Validation**: Pydantic models for all configs
- **Async**: All agent execution is async
- **Line length**: 120 characters (ruff)
- **Imports**: Always at top of file
- **No defensive programming**: Flat, expressive style
- **No backwards compatible aliases**: Ever

## Adding New Agents

1. Create config: `configs/my_agent.json`
2. Add enum: `AgentKey.MY_AGENT` in `agent_types.py`
3. Auto-discovered via `discover_and_register_agents()`
4. Run server: `glyx-mcp` (tool available automatically)

## HITL (Human-in-the-Loop)

### Mechanism (Pydantic AI)
- `ApprovalRequired` exception raised by tools needing approval
- Agent returns `DeferredToolRequests`
- User prompted via `ask_user()` tool
- Resume with `DeferredToolResults`

### ask_user Tool
```python
async def ask_user(question: str, ctx: Context, expected_format: str) -> str
# Uses ctx.elicit() for structured responses
# Fallback to ctx.info() if not supported
```

## Key File References

| Component | File | Purpose |
|-----------|------|---------|
| MCP Server | `src/glyx_mcp/server.py` | Tool registration, entry point |
| HTTP Server | `src/api/server.py` | FastAPI + MCP combined |
| Agent Registry | `src/python-sdk/.../registry.py` | Agent discovery |
| Agent Execution | `src/python-sdk/.../composable_agents.py` | JSON→CLI wrapper |
| Device Dispatch | `src/python-sdk/.../tools/device_dispatch.py` | iOS dispatch |
| WebSocket | `src/python-sdk/.../websocket_manager.py` | Real-time events |
| Settings | `src/python-sdk/.../settings.py` | Configuration |
| Tasks API | `src/api/routes/tasks.py` | Task CRUD + notifications |
| GitHub Webhook | `src/api/webhooks/github.py` | GitHub events |
| Notifications | `src/api/models/notifications.py` | Payload models |

# Glyx-MCP Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              PRESENTATION LAYER                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐              │
│  │  Landing Page   │    │   Claude Code   │    │  MCP Clients    │              │
│  │  (Next.js 16)   │    │   (stdio MCP)   │    │  (HTTP/SSE)     │              │
│  │  Vercel         │    │                 │    │                 │              │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘              │
│           │                      │                      │                        │
│           │              stdio   │              HTTP    │                        │
└───────────┼──────────────────────┼──────────────────────┼────────────────────────┘
            │                      │                      │
            ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            API GATEWAY LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                    FastAPI + FastMCP Combined Server                     │    │
│  │                         (Uvicorn @ port 8000/8080)                       │    │
│  ├─────────────────────────────────────────────────────────────────────────┤    │
│  │                                                                          │    │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐       │    │
│  │  │   MCP Protocol   │  │    REST API      │  │    WebSocket     │       │    │
│  │  │   /mcp           │  │    /api/*        │  │    /ws           │       │    │
│  │  │                  │  │                  │  │                  │       │    │
│  │  │  • Tool calls    │  │  • /healthz      │  │  • Real-time     │       │    │
│  │  │  • Resources     │  │  • /api/agents   │  │    events        │       │    │
│  │  │  • Prompts       │  │  • /api/auth/*   │  │  • Broadcast     │       │    │
│  │  │                  │  │  • /api/orgs/*   │  │    updates       │       │    │
│  │  │                  │  │  • /api/memory/* │  │                  │       │    │
│  │  │                  │  │  • /stream/*     │  │                  │       │    │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘       │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
└──────────────────────────────────┬───────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           AGENT CORE LAYER                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                         Agent Registry                                   │    │
│  │              (discover_and_register_agents)                              │    │
│  ├─────────────────────────────────────────────────────────────────────────┤    │
│  │                                                                          │    │
│  │  agents/*.json ──────────► Auto-discovery ◄────────── Supabase agents   │    │
│  │                                  │                     table             │    │
│  │                                  ▼                                       │    │
│  │                        MCP Tool Registration                             │    │
│  │                        (use_aider, use_cursor, ...)                      │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                       ComposableAgent                                    │    │
│  │                   (src/glyx/core/agent.py)                               │    │
│  ├─────────────────────────────────────────────────────────────────────────┤    │
│  │                                                                          │    │
│  │   AgentConfig (JSON)                                                     │    │
│  │        │                                                                 │    │
│  │        ▼                                                                 │    │
│  │   TaskConfig (Pydantic)                                                  │    │
│  │        │                                                                 │    │
│  │        ▼                                                                 │    │
│  │   CLI Command Builder ──────► asyncio.subprocess ──────► AgentResult     │    │
│  │                                     │                                    │    │
│  │                                     ▼                                    │    │
│  │                              stdout/stderr streaming                     │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                         Orchestrator                                     │    │
│  │            (src/glyx/mcp/orchestration/orchestrator.py)                  │    │
│  ├─────────────────────────────────────────────────────────────────────────┤    │
│  │                                                                          │    │
│  │   OpenAI Agents SDK                                                      │    │
│  │        │                                                                 │    │
│  │        ├──► use_aider_agent()                                            │    │
│  │        ├──► use_grok_agent()                                             │    │
│  │        ├──► use_claude_agent()                                           │    │
│  │        ├──► use_codex_agent()                                            │    │
│  │        ├──► search_memory()                                              │    │
│  │        ├──► save_memory()                                                │    │
│  │        ├──► create_task() / update_task()                                │    │
│  │        └──► ask_user()                                                   │    │
│  │                                                                          │    │
│  │   Forced Memory Saving ──────► MemorySaver agent (tool_choice forced)    │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                      Wrapped CLI Agents                                  │    │
│  ├──────────┬──────────┬──────────┬──────────┬──────────┬─────────────────┤    │
│  │  aider   │  cursor  │  claude  │  grok    │ opencode │  + 5 more       │    │
│  │  (code)  │  (cloud) │  (cli)   │  (xAI)   │  (multi) │  agents         │    │
│  └──────────┴──────────┴──────────┴──────────┴──────────┴─────────────────┘    │
│                                                                                  │
└──────────────────────────────────┬───────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                             DATA LAYER                                           │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐      │
│  │      Supabase       │  │       Mem0          │  │      SQLite         │      │
│  │   (PostgreSQL)      │  │   (Semantic Memory) │  │   (Sessions)        │      │
│  ├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤      │
│  │                     │  │                     │  │                     │      │
│  │  Tables:            │  │  Categories:        │  │  Table: items       │      │
│  │  • organizations    │  │  • architecture     │  │  • session_id       │      │
│  │  • agents           │  │  • integrations     │  │  • role             │      │
│  │  • activities       │  │  • code_style       │  │  • content          │      │
│  │  • tasks            │  │  • project_id       │  │  • created_at       │      │
│  │                     │  │  • observability    │  │                     │      │
│  │  Auth:              │  │  • product          │  │  Path:              │      │
│  │  • Users            │  │  • key_concept      │  │  /tmp/glyx_sessions │      │
│  │  • Sessions         │  │  • tasks            │  │  .db                │      │
│  │  • JWT tokens       │  │                     │  │                     │      │
│  │                     │  │  Graph Relations    │  │                     │      │
│  │  Realtime:          │  │  (enable_graph)     │  │                     │      │
│  │  • WebSocket sync   │  │                     │  │                     │      │
│  │                     │  │                     │  │                     │      │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘      │
│                                                                                  │
└──────────────────────────────────┬───────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          INFRASTRUCTURE LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                           Fly.io                                         │    │
│  │                      (glyx-mcp.fly.dev)                                  │    │
│  ├─────────────────────────────────────────────────────────────────────────┤    │
│  │  Region: sjc (San Jose)                                                  │    │
│  │  VM: 1 CPU (shared), 1GB RAM                                             │    │
│  │  Port: 8080 (internal)                                                   │    │
│  │  Health: GET /api/healthz                                                │    │
│  │  Auto-start: enabled, Auto-stop: disabled                                │    │
│  │  Min machines: 1                                                         │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                           Docker                                         │    │
│  │                    (python:3.12-slim)                                    │    │
│  ├─────────────────────────────────────────────────────────────────────────┤    │
│  │  Installed Tools:                                                        │    │
│  │  • uv (package manager)                                                  │    │
│  │  • OpenCode CLI                                                          │    │
│  │  • Claude Code CLI (npm)                                                 │    │
│  │  • cursor-agent                                                          │    │
│  │                                                                          │    │
│  │  Entrypoint: python -m glyx.mcp.server --http                            │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                        Observability                                     │    │
│  ├─────────────────────────────────────────────────────────────────────────┤    │
│  │                                                                          │    │
│  │  Langfuse (Optional)           │  OpenTelemetry                          │    │
│  │  • LLM tracing                 │  • Distributed tracing                  │    │
│  │  • OpenAI agent instrumentation│  • OTLP HTTP export                     │    │
│  │  • us.cloud.langfuse.com       │  • OpenInference conventions            │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Presentation Layer

| Component | Technology | Deployment | Status |
|-----------|------------|------------|--------|
| Landing Page | Next.js 16, TypeScript, Tailwind, shadcn/ui | Vercel | In git history |
| Claude Code | stdio MCP protocol | Local | Active |
| MCP Clients | HTTP + SSE | Any | Active |

### 2. API Gateway Layer

**Combined Server Pattern:**
```python
# src/glyx/mcp/server.py
mcp_app = mcp.http_app(path='/mcp')
combined_app = FastAPI(
    routes=[*mcp_app.routes, *api_app.routes],
    lifespan=mcp_app.lifespan,
)
```

**REST Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/healthz` | GET | Health check |
| `/api/agents` | GET | List available agents |
| `/api/auth/signup` | POST | User registration (Supabase Auth) |
| `/api/auth/signin` | POST | User login |
| `/api/auth/signout` | POST | User logout |
| `/api/auth/user` | GET | Get current user (JWT required) |
| `/api/organizations` | GET/POST | Organization CRUD |
| `/api/organizations/{id}` | GET/DELETE | Organization by ID |
| `/api/features` | GET/POST | Feature pipeline CRUD |
| `/api/features/{id}` | GET/PATCH/DELETE | Feature by ID |
| `/api/memory/save` | POST | Save memory via REST |
| `/api/memory/search` | POST | Search memory via REST |
| `/stream/cursor` | POST | Stream cursor agent (SSE) |
| `/ws` | WebSocket | Real-time event broadcasting |

### 3. Agent Core Layer

**Agent Configuration Schema:**
```json
{
  "agent_key": "aider",
  "command": "aider",
  "args": {
    "prompt": {"flag": "--message", "type": "string", "required": true},
    "model": {"flag": "--model", "type": "string", "default": "gpt-5"},
    "files": {"flag": "--file", "type": "string", "required": false}
  },
  "description": "AI code editor",
  "capabilities": ["code_generation", "refactoring"]
}
```

**Available Agents:**

| Agent | CLI | Purpose |
|-------|-----|---------|
| aider | `aider` | AI pair programmer |
| cursor | `cursor-agent` | Cloud autonomous coding |
| claude | `claude` | Claude Code CLI |
| grok | `opencode run` | xAI reasoning |
| opencode | `opencode` | Multi-purpose |
| codex | `codex` | Code generation |
| gemini | `gemini` | Google Gemini |
| deepseek_r1 | `deepseek` | DeepSeek reasoning |
| kimi_k2 | `kimi` | Kimi K2 model |
| shot_scraper | `shot-scraper` | Screenshot automation |

**Execution Flow:**
```
AgentConfig (JSON)
      │
      ▼
TaskConfig (prompt, model, files, ...)
      │
      ▼
CLI Command Builder
      │
      ▼
asyncio.create_subprocess_exec()
      │
      ├──► stdout streaming ──► ctx.info() / SSE
      │
      └──► AgentResult (stdout, stderr, exit_code, execution_time)
```

### 4. Data Layer

**Supabase Tables:**

```sql
-- organizations
CREATE TABLE organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  template TEXT,
  config JSONB DEFAULT '{}',
  status TEXT DEFAULT 'draft',
  stages JSONB DEFAULT '[]',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- agents (dynamic agent registry)
CREATE TABLE agents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_key TEXT UNIQUE NOT NULL,
  command TEXT NOT NULL,
  args JSONB NOT NULL,
  user_id UUID,  -- NULL for global agents
  description TEXT,
  version TEXT,
  capabilities TEXT[],
  is_active BOOLEAN DEFAULT true
);

-- activities (audit log)
CREATE TABLE activities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID,
  org_name TEXT,
  actor TEXT NOT NULL,  -- 'agent' or 'user'
  type TEXT NOT NULL,   -- MESSAGE, CODE, TOOL_CALL, etc.
  role TEXT,
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

**Mem0 Categories:**
- `architecture` - System design, patterns
- `integrations` - MCP tools, APIs
- `code_style_guidelines` - Conventions
- `project_id` - Project identity
- `observability` - Logging, tracing
- `product` - Features
- `key_concept` - Important patterns
- `tasks` - Task tracking

### 5. Infrastructure Layer

**Fly.io Configuration (fly.toml):**
```toml
app = "glyx-mcp"
primary_region = "sjc"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 1

[[vm]]
  memory = "1gb"
  cpu_kind = "shared"
  cpus = 1
```

**Docker Layers:**
```dockerfile
FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y git curl unzip nodejs npm

# uv package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Agent CLIs
RUN curl -sSL https://opencode.ai/install.sh | sh
RUN npm install -g @anthropic-ai/claude-code
RUN # cursor-agent installation

# Application
WORKDIR /app
COPY . .
RUN uv sync

CMD ["python", "-m", "glyx.mcp.server", "--http"]
```

## Data Flow Diagrams

### MCP Tool Call Flow

```
Claude Code                    glyx-mcp Server                    External
    │                               │                                │
    │  use_aider(prompt, files)     │                                │
    │──────────────────────────────►│                                │
    │                               │  Load AgentConfig              │
    │                               │  Build CLI command             │
    │                               │                                │
    │                               │  aider --message "..." --file  │
    │                               │───────────────────────────────►│
    │                               │                                │
    │                               │◄─────────────────────────────  │
    │                               │  stdout/stderr streaming       │
    │                               │                                │
    │◄──────────────────────────────│  AgentResult.output            │
    │                               │                                │
```

### Orchestration Flow

```
User Task                      Orchestrator                      Agents
    │                               │                               │
    │  orchestrate("Build auth")    │                               │
    │──────────────────────────────►│                               │
    │                               │  search_memory(context)       │
    │                               │──────────────────────────────►│ Mem0
    │                               │◄──────────────────────────────│
    │                               │                               │
    │                               │  create_task(...)             │
    │                               │──────────────────────────────►│ Supabase
    │                               │                               │
    │                               │  use_aider_agent(...)         │
    │                               │──────────────────────────────►│ aider CLI
    │                               │◄──────────────────────────────│
    │                               │                               │
    │                               │  use_claude_agent(...)        │
    │                               │──────────────────────────────►│ claude CLI
    │                               │◄──────────────────────────────│
    │                               │                               │
    │                               │  _force_memory_save()         │
    │                               │──────────────────────────────►│ Mem0
    │                               │                               │
    │◄──────────────────────────────│  OrchestratorResult           │
    │                               │                               │
```

## Dependencies

### Core Stack

| Category | Package | Version | Purpose |
|----------|---------|---------|---------|
| MCP | fastmcp | 2.13.0 | MCP protocol server |
| Web | fastapi | 0.122.0 | REST API framework |
| Server | uvicorn | 0.38.0 | ASGI server |
| Validation | pydantic | 2.12.3 | Data validation |
| AI | openai | 2.6.1 | OpenAI API |
| AI | openai-agents | 0.4.2 | Agent orchestration |
| Database | supabase | 2.24.0 | PostgreSQL + Auth |
| Memory | mem0ai | 1.0.0 | Semantic memory |
| Tracing | langfuse | 3.8.1 | LLM observability |

### Development

| Tool | Purpose |
|------|---------|
| uv | Package management |
| ruff | Linting (120 char lines) |
| mypy | Type checking (strict mode) |
| pytest | Testing (40% coverage threshold) |

## Entry Points

```bash
# MCP server (stdio mode for Claude Code)
glyx-mcp

# HTTP server (for REST API + WebSocket)
glyx-mcp-http

# Development
uv run python src/glyx/mcp/server.py
```

## Environment Variables

```bash
# Required
OPENAI_API_KEY=
SUPABASE_URL=
SUPABASE_ANON_KEY=

# Optional
ANTHROPIC_API_KEY=
OPENROUTER_API_KEY=
MEM0_API_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=

# Defaults
PORT=8000
DEFAULT_ORCHESTRATOR_MODEL=gpt-5
```

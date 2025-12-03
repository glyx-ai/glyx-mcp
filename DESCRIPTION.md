# glyx-mcp: Composable AI Agent Framework

A FastMCP server that provides composable AI agent wrappers. Agents are defined via JSON configs and exposed as MCP tools, executed as subprocesses for reliability and observability.

## Core Concepts

### • **JSON-Driven Agent Configuration**
Agents are defined as JSON configs that map to CLI commands. No code changes needed to add new agents.

```json
{
  "aider": {
    "command": "aider",
    "args": {
      "prompt": {
        "flag": "--message",
        "type": "string",
        "required": true
      },
      "model": {
        "flag": "--model",
        "type": "string",
        "default": "gpt-5"
      },
      "files": {
        "flag": "--file",
        "type": "string",
        "required": true
      },
      "no_git": {
        "flag": "--no-git",
        "type": "bool",
        "default": true
      }
    }
  }
}
```

### • **ComposableAgent: JSON → CLI → Subprocess**
The core execution engine transforms JSON configs into CLI commands and runs them as subprocesses.

```python
from glyx.core.agent import ComposableAgent, AgentKey

# Load agent from config
agent = ComposableAgent.from_key(AgentKey.AIDER)

# Execute with task config
result = await agent.execute({
    "prompt": "Add error handling",
    "files": "src/api.py",
    "model": "gpt-5"
}, timeout=300)

# Structured result
print(result.stdout)      # Command output
print(result.exit_code)   # 0 = success
print(result.execution_time)  # Seconds
```

### • **Auto-Discovery and Registration**
Agents are automatically discovered from JSON files and registered as MCP tools at startup.

```python
# In server.py
from glyx.core.registry import discover_and_register_agents

agents_dir = Path("agents")
discover_and_register_agents(mcp, agents_dir)
# Creates MCP tools: use_aider, use_grok, use_claude, etc.
```

### • **Multiple Transport Modes**
Supports stdio (Claude Code), HTTP (web), and WebSocket (realtime) transports.

```python
# Stdio mode (default)
glyx-mcp

# HTTP mode
glyx-mcp-http  # Serves on port 8000

# WebSocket events
ws://localhost:8001/ws  # Real-time agent updates
```

## Key Features

### • **Agent Execution with Progress Reporting**
Agents stream progress updates via FastMCP context, WebSocket broadcasts, and async generators.

```python
async def use_aider(prompt: str, files: str, ctx: Context) -> str:
    await ctx.info("🚀 Starting Aider execution")
    
    agent = ComposableAgent.from_key(AgentKey.AIDER)
    result = await agent.execute({
        "prompt": prompt,
        "files": files
    }, timeout=300, ctx=ctx)
    
    # Progress updates automatically sent via ctx.info()
    return result.output
```

### • **Streaming Execution**
Support for real-time event streaming via async generators (NDJSON parsing).

```python
async for event in agent.execute_stream(task_config, timeout=600):
    # Events: agent_event, agent_output, agent_error, agent_complete
    print(event)
    # {"type": "agent_event", "event": {...}, "timestamp": "..."}
```

### • **Memory System (Mem0 Integration)**
Vector-based memory storage for project context, architecture decisions, and patterns.

```python
# Save memory with categories
save_memory(
    content="We use FastMCP for MCP server implementation",
    agent_id="orchestrator",
    run_id="run-123",
    category="architecture"
)

# Search memories
memories = search_memory(
    query="How do we handle MCP tool registration?",
    limit=5,
    category="architecture"
)
```

### • **Session Management**
Conversation history persistence using SQLite sessions.

```python
# Sessions automatically created per conversation_id
# History loaded and injected into prompts
# Messages saved after each agent call
```

### • **Orchestration**
Coordinates multiple agents using OpenAI Agents SDK for complex multi-step tasks.

```python
@mcp.tool
async def orchestrate(task: str, ctx: Context) -> str:
    orchestrator = Orchestrator(ctx=ctx, model="gpt-5")
    result = await orchestrator.orchestrate(task)
    return result.output

# Orchestrator has access to:
# - use_aider_agent, use_grok_agent, use_claude_agent, etc.
# - search_memory, save_memory
# - create_task, assign_task, update_task
# - ask_user (for clarification)
```

### • **Task Tracking**
Standalone task management server (`glyx-tasks`) with MCP tools.

```python
# Task tools available to orchestrator
create_task(title="Implement auth", description="...")
assign_task(task_id="123", agent="aider")
update_task(task_id="123", status="in_progress")
```

## Architecture

### • **Agent Config → CLI Args → Subprocess**
Flow: `AgentConfig (JSON) → ComposableAgent.execute() → subprocess → AgentResult`

```python
class ComposableAgent:
    def __init__(self, config: AgentConfig):
        self.config = config
    
    async def execute(self, task_config: dict, timeout: int, ctx=None) -> AgentResult:
        cmd = [self.config.command]
        
        # Build CLI args from config
        for key, arg_spec in self.config.args.items():
            value = task_config.get(key, arg_spec.default)
            if value is not None:
                if arg_spec.flag:
                    if arg_spec.type == "bool" and value:
                        cmd.append(arg_spec.flag)
                    else:
                        cmd.extend([arg_spec.flag, str(value)])
                else:  # Positional arg
                    cmd.append(str(value))
        
        # Execute subprocess
        process = await asyncio.create_subprocess_exec(*cmd, ...)
        # ... handle stdout/stderr, timeout, etc.
        
        return AgentResult(stdout=..., stderr=..., exit_code=...)
```

### • **Pydantic Validation**
All configs validated with Pydantic models for type safety.

```python
class AgentConfig(BaseModel):
    agent_key: str
    command: str = Field(..., min_length=1)
    args: dict[str, ArgSpec]
    description: str | None = None
    capabilities: list[str] = Field(default_factory=list)

class ArgSpec(BaseModel):
    flag: str = ""  # Empty for positional args
    type: Literal["string", "bool", "int"] = "string"
    required: bool = False
    default: str | int | bool | None = None
```

### • **Real-time Updates**
Three mechanisms for progress reporting:

1. **FastMCP Context** (`ctx.info()`): For Claude Code MCP integration
2. **WebSocket Broadcasts** (`broadcast_event()`): For web UI and browser extensions
3. **Async Generators** (`execute_stream()`): For HTTP streaming endpoints

```python
# WebSocket broadcast
await broadcast_event("agent.start", {
    "agent_key": "aider",
    "command": ["aider", "--message", "..."]
})

# FastMCP context
await ctx.info("🚀 Starting execution")

# Streaming
async for event in agent.execute_stream(...):
    yield event
```

## Example Agents

### • **Aider** - Code Editing
```python
# Config: agents/aider.json
# Command: aider --message "..." --file "src/api.py" --model "gpt-5"

use_aider(
    prompt="Add error handling to the API endpoint",
    files="src/api.py,src/models.py",
    model="gpt-5"
)
```

### • **Grok** - General Reasoning
```python
# Config: agents/grok.json
# Command: opencode run --model "openrouter/x-ai/grok-code-fast-1" "..."

use_grok(
    prompt="Explain the difference between async and sync Python",
    model="openrouter/x-ai/grok-code-fast-1"
)
```

### • **Claude Code** - Complex Tasks
```python
# Config: agents/claude.json
# Command: claude-code --prompt "..." --model "claude-sonnet-4"

use_claude(
    prompt="Refactor the authentication system",
    model="claude-sonnet-4-20250514",
    max_turns=30
)
```

## Testing Strategy

### • **Three Test Tiers**
1. **Unit tests** (no marker): Mocked subprocess, fast
2. **Integration tests** (`@pytest.mark.integration`): Mock CLIs, subprocess execution
3. **E2E tests** (`@pytest.mark.e2e`): Real CLIs + API keys required

```python
@pytest.mark.integration
async def test_aider_execution():
    agent = ComposableAgent.from_key(AgentKey.AIDER)
    result = await agent.execute({"prompt": "test", "files": "test.py"})
    assert result.success
```

## Deployment

### • **Docker Compose** (Recommended)
```yaml
# compose.yml
services:
  glyx-mcp:
    build: .
    command: glyx-mcp
    env_file: .env
    volumes:
      - .:/workspace  # Mount project for file editing
```

### • **Fly.io** (Production)
```bash
fly deploy  # Uses Dockerfile
# Serves HTTP MCP at https://glyx-mcp.fly.dev/mcp
```

## Environment Variables

```bash
# API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-...
MEM0_API_KEY=...

# Optional Tracing
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://cloud.langfuse.com

# Model Defaults
DEFAULT_ORCHESTRATOR_MODEL=gpt-5
DEFAULT_AIDER_MODEL=gpt-5
DEFAULT_GROK_MODEL=openrouter/x-ai/grok-4-fast
```

## Adding a New Agent

1. **Create JSON config** in `agents/my_agent.json`
2. **Add enum** `AgentKey.MY_AGENT` in `agent.py`
3. **Auto-registered** as `use_my_agent` MCP tool
4. **No code changes needed** - discovery handles registration

```json
{
  "my_agent": {
    "command": "my-cli-tool",
    "args": {
      "prompt": {"flag": "--prompt", "type": "string", "required": true},
      "model": {"flag": "--model", "type": "string", "default": "gpt-5"}
    },
    "description": "My custom agent"
  }
}
```

## Key Design Principles

• **Composable by config**: Add agents via JSON, no code changes
• **Subprocess execution**: Isolated, reliable, observable
• **Type-safe**: Strict mypy, Pydantic validation
• **Async-first**: All operations are async
• **Progress reporting**: Multiple channels (context, WebSocket, streaming)
• **Memory-aware**: Vector memory for context retention
• **Orchestration-ready**: Multi-agent coordination built-in

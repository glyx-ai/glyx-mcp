# Glyx Python SDK

Python SDK for the Glyx AI orchestration framework. This package provides composable AI agent wrappers, orchestration capabilities, and memory management for building intelligent coding assistants.

## Installation

```bash
pip install glyx-python-sdk
```

For development:

```bash
pip install glyx-python-sdk[dev]
```

## Quick Start

### Using Composable Agents

```python
from glyx_sdk import ComposableAgent, AgentKey

# Create an agent from a predefined key
agent = ComposableAgent.from_key(AgentKey.AIDER)

# Execute a task
result = await agent.execute({
    "prompt": "Add error handling to auth.py",
    "files": "src/auth.py",
    "model": "gpt-5"
}, timeout=300)

print(result.output)
```

### Using the Orchestrator

```python
from glyx_sdk import GlyxOrchestrator

# Create an orchestrator
orchestrator = GlyxOrchestrator(
    agent_name="MyOrchestrator",
    model="openrouter/anthropic/claude-sonnet-4",
    session_id="my-session"
)

# Run a prompt and stream results
async for item in orchestrator.run_prompt_streamed_items("Implement user authentication"):
    print(item)

await orchestrator.cleanup()
```

### Memory Management

```python
from glyx_sdk import save_memory, search_memory

# Save a memory
save_memory(
    content="Project uses FastMCP framework with OpenAI Agents SDK",
    agent_id="orchestrator",
    run_id="run-123",
    category="architecture"
)

# Search memories
results = search_memory(
    query="authentication patterns",
    limit=5,
    category="architecture"
)
```

### Pipeline Management

```python
from glyx_sdk import Pipeline, FeatureCreate

# Create a feature pipeline
pipeline = Pipeline.create(FeatureCreate(
    name="User Authentication",
    description="Implement JWT-based authentication"
))

# Run a pipeline stage
artifact = await pipeline.run_stage(
    stage_id=pipeline.feature.stages[0].id,
    prompt="Implement the authentication middleware"
)
```

## Features

- **Composable Agents**: JSON-driven CLI wrappers for AI agents (Aider, Claude, Grok, etc.)
- **Orchestration**: Coordinate multiple agents for complex workflows
- **Memory Management**: Store and retrieve project context using Mem0
- **Pipeline Support**: Multi-stage feature development workflows
- **Type Safety**: Full Pydantic validation and type hints
- **Async-first**: Built on asyncio for concurrent operations

## Agent Types

The SDK supports several pre-configured agents:

- **AIDER**: AI pair programmer for code editing
- **CLAUDE**: Advanced reasoning and complex workflows
- **GROK**: Fast reasoning and analysis
- **CODEX**: Code generation
- **OPENCODE**: General-purpose coding tasks
- **CURSOR**: Cursor agent integration
- **GEMINI**: Google Gemini integration

## Configuration

The SDK uses environment variables for configuration:

```bash
# API Keys
OPENAI_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
OPENROUTER_API_KEY=your_key
MEM0_API_KEY=your_key

# Supabase (optional)
SUPABASE_URL=your_url
SUPABASE_ANON_KEY=your_key

# Model Configuration
DEFAULT_ORCHESTRATOR_MODEL=gpt-5
DEFAULT_AIDER_MODEL=gpt-5
```

Or use the `Settings` class:

```python
from glyx_sdk import settings

print(settings.openai_api_key)
```

## Development

### Setup

```bash
git clone https://github.com/htelsiz/glyx-mcp.git
cd glyx-mcp/packages/sdk
uv pip install -e ".[dev]"
```

### Testing

```bash
pytest
pytest -m integration  # Integration tests
```

### Type Checking

```bash
mypy src/
```

### Linting

```bash
ruff check src/
```

## Documentation

For more information, see the [main Glyx documentation](https://github.com/htelsiz/glyx-mcp/blob/main/README.md).

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## Links

- [GitHub Repository](https://github.com/htelsiz/glyx-mcp)
- [PyPI Package](https://pypi.org/project/glyx-python-sdk/)
- [Documentation](https://github.com/htelsiz/glyx-mcp/blob/main/README.md)

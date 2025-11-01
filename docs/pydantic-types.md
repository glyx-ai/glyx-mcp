# Pydantic Types Documentation

This document provides comprehensive documentation for all Pydantic models and structured types in glyx-mcp.

## Table of Contents

- [Core Agent Types](#core-agent-types)
  - [ArgSpec](#argspec)
  - [AgentConfig](#agentconfig)
  - [TaskConfig](#taskconfig)
  - [AgentResult](#agentresult)
- [Orchestrator Types](#orchestrator-types)
  - [AgentTask](#agenttask)
  - [ExecutionPlan](#executionplan)
  - [OrchestratorResult](#orchestratorresult)
- [Prompt Configuration](#prompt-configuration)
  - [PromptConfig](#promptconfig)

---

## Core Agent Types

### ArgSpec

**Location**: `src/glyx_mcp/composable_agent.py:75`

Specification for a single command-line argument. Maps JSON config fields to CLI flags and handles type conversion.

#### Fields

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `flag` | `str` | `""` | No | CLI flag (e.g., `"--model"`). Empty string for positional arguments. |
| `type` | `Literal["string", "bool", "int"]` | `"string"` | No | Argument type for validation and conversion. |
| `required` | `bool` | `False` | No | Whether the argument is required. |
| `default` | `str \| int \| bool \| None` | `None` | No | Default value if not provided in task config. |
| `description` | `str` | `""` | No | Human-readable description of the argument. |

#### Validators

- **`validate_type`**: Ensures `type` is one of `"string"`, `"bool"`, or `"int"`. Raises `ValueError` for invalid types.

#### Usage Example

```json
{
  "prompt": {
    "flag": "--prompt",
    "type": "string",
    "required": true,
    "description": "The task prompt"
  },
  "model": {
    "flag": "--model",
    "type": "string",
    "default": "gpt-5",
    "description": "Model to use"
  },
  "verbose": {
    "flag": "--verbose",
    "type": "bool",
    "description": "Enable verbose output"
  }
}
```

#### Behavior Notes

- **Positional args**: Use `"flag": ""` (empty string)
- **Boolean flags**: Only included in command if value is `True`
- **Type conversion**: Values are converted to strings when building CLI commands

---

### AgentConfig

**Location**: `src/glyx_mcp/composable_agent.py:92`

Agent configuration loaded from JSON files. Defines how an agent maps to a CLI command.

#### Fields

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `agent_key` | `str` | - | Yes | Unique identifier for the agent (e.g., "aider", "grok"). |
| `command` | `str` | - | Yes | Base CLI command to execute. Must be non-empty. |
| `args` | `dict[str, ArgSpec]` | - | Yes | Mapping of parameter names to argument specifications. |
| `description` | `str \| None` | `None` | No | Human-readable description of the agent. |
| `version` | `str \| None` | `None` | No | Version of the agent or CLI tool. |
| `capabilities` | `list[str]` | `[]` | No | List of agent capabilities (e.g., "code-editing", "reasoning"). |

#### Field Validators

- **`command`**: Enforced to be non-empty via `Field(..., min_length=1)`

#### Methods

##### `from_file(file_path: str | Path) -> AgentConfig`

Load and validate agent configuration from JSON file.

**Args:**
- `file_path`: Path to JSON config file

**Returns:**
- Validated `AgentConfig` instance

**Raises:**
- `ValidationError`: If JSON structure is invalid
- `FileNotFoundError`: If file doesn't exist

**Example:**
```python
config = AgentConfig.from_file("src/glyx_mcp/config/aider.json")
```

#### File Format Example

```json
{
  "aider": {
    "command": "aider",
    "description": "AI-powered code editing",
    "args": {
      "prompt": {
        "flag": "",
        "type": "string",
        "required": true
      },
      "files": {
        "flag": "--files",
        "type": "string",
        "required": true
      }
    }
  }
}
```

---

### TaskConfig

**Location**: `src/glyx_mcp/composable_agent.py:115`

Task configuration for agent execution. Validated with Pydantic and passed to `ComposableAgent.execute()`.

#### Fields

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `prompt` | `str` | - | Yes | Task prompt or instruction. Must be non-empty. |
| `model` | `str` | `"gpt-5"` | No | Model to use for execution. |
| `files` | `str \| None` | `None` | No | Comma-separated file paths for file-based tools. |
| `read_files` | `str \| None` | `None` | No | Read-only reference files (comma-separated). |
| `working_dir` | `str \| None` | `None` | No | Working directory for command execution. |
| `max_turns` | `int \| None` | `None` | No | Maximum conversation turns for multi-turn agents. |

#### Configuration

- **`model_config`**: `{"extra": "allow"}` - Allows additional fields for extensibility

#### Usage Example

```python
task = TaskConfig(
    prompt="Add error handling to the login function",
    model="gpt-5",
    files="src/auth.py,tests/test_auth.py"
)

# Or as dict (common in MCP tools)
task_dict = {
    "prompt": "Refactor this function",
    "files": "src/utils.py",
    "model": "claude-3-opus"
}
```

---

### AgentResult

**Location**: `src/glyx_mcp/composable_agent.py:51`

**Note**: This is a `@dataclass`, not a Pydantic model, but documented here for completeness.

Structured result from agent execution containing subprocess output and metadata.

#### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `stdout` | `str` | - | Standard output from the subprocess. |
| `stderr` | `str` | - | Standard error from the subprocess. |
| `exit_code` | `int` | - | Process exit code (0 = success). |
| `timed_out` | `bool` | `False` | Whether execution exceeded timeout. |
| `execution_time` | `float` | `0.0` | Execution time in seconds. |
| `command` | `list[str] \| None` | `None` | The actual CLI command that was executed. |

#### Properties

##### `success -> bool`
Returns `True` if `exit_code == 0` and `timed_out == False`.

##### `output -> str`
Returns combined output: `stdout` + `stderr` (prefixed with "STDERR:"). Provided for backward compatibility.

#### Usage Example

```python
result = await agent.execute(task_config)

if result.success:
    print(f"Success! Output: {result.stdout}")
else:
    print(f"Failed with exit code {result.exit_code}")
    print(f"Error: {result.stderr}")
```

---

## Orchestrator Types

### AgentTask

**Location**: `src/glyx_mcp/agents/orchestrator.py:25`

A task to be executed by a specific agent as part of an orchestration plan.

#### Fields

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `agent` | `str` | - | Yes | Agent name (e.g., "aider", "grok", "codex"). Must match `AgentKey` enum. |
| `task_description` | `str` | - | Yes | Human-readable description of what the agent should do. |
| `parameters` | `dict[str, Any]` | `{}` | No | Parameters to pass to the agent (matches `TaskConfig` fields). |

#### Usage Example

```python
task = AgentTask(
    agent="aider",
    task_description="Add unit tests for the new feature",
    parameters={
        "prompt": "Add comprehensive unit tests",
        "files": "src/features/new_feature.py,tests/test_new_feature.py",
        "model": "gpt-5"
    }
)
```

---

### ExecutionPlan

**Location**: `src/glyx_mcp/agents/orchestrator.py:33`

Plan for executing multiple agents in sequence. Created by GPT-5 during orchestration planning.

#### Fields

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `reasoning` | `str` | - | Yes | Explanation of why this plan was chosen and the approach. |
| `tasks` | `list[AgentTask]` | - | Yes | Ordered list of agent tasks to execute sequentially. |

#### Usage Example

```python
plan = ExecutionPlan(
    reasoning="First use aider to refactor the code, then grok to analyze potential issues",
    tasks=[
        AgentTask(
            agent="aider",
            task_description="Refactor authentication logic",
            parameters={"prompt": "Extract auth to service", "files": "src/auth.py"}
        ),
        AgentTask(
            agent="grok",
            task_description="Analyze security implications",
            parameters={"prompt": "Review auth service for vulnerabilities"}
        )
    ]
)
```

---

### OrchestratorResult

**Location**: `src/glyx_mcp/agents/orchestrator.py:40`

Complete result from orchestrator execution including plan, individual agent results, and synthesis.

#### Fields

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `success` | `bool` | - | Yes | Whether overall orchestration succeeded (all agents successful). |
| `plan` | `ExecutionPlan \| None` | `None` | No | The execution plan that was created and executed. |
| `agent_results` | `list[dict[str, Any]]` | `[]` | No | Results from each agent execution with metadata. |
| `synthesis` | `str` | - | Yes | Final synthesized response from GPT-5 combining all agent outputs. |
| `error` | `str \| None` | `None` | No | Error message if orchestration failed. |

#### Agent Result Dictionary Structure

Each item in `agent_results` contains:

```python
{
    "agent": str,              # Agent name
    "task": str,               # Task description
    "success": bool,           # Whether agent succeeded
    "output": str,             # Agent output
    "exit_code": int,          # Exit code
    "execution_time": float,   # Time in seconds
    "error": str | None        # Error message if failed
}
```

#### Usage Example

```python
result = await orchestrator.orchestrate("Add tests and review code")

if result.success:
    print(f"Synthesis: {result.synthesis}")
    for agent_result in result.agent_results:
        print(f"{agent_result['agent']}: {agent_result['success']}")
else:
    print(f"Failed: {result.error}")
```

---

## Prompt Configuration

### PromptConfig

**Location**: `src/glyx_mcp/prompt_config.py:15`

Configuration for which MCP prompts are enabled in the server.

#### Fields

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `enabled_prompts` | `list[str]` | `["agent"]` | No | List of prompt names to enable. |

#### Default Behavior

- If no config file exists, only the `"agent"` prompt is enabled
- Config file location: `.glyx-mcp-prompts.json` (current directory or home directory)

#### Usage Example

**Config File** (`.glyx-mcp-prompts.json`):
```json
{
  "enabled_prompts": ["agent", "orchestrate", "aider"]
}
```

**Code**:
```python
from glyx_mcp.prompt_config import load_prompt_config, is_prompt_enabled

config = load_prompt_config()
print(config.enabled_prompts)  # ["agent", "orchestrate", "aider"]

if is_prompt_enabled("orchestrate"):
    # Register orchestrate prompt
    pass
```

---

## Validation Best Practices

### 1. Always Use Pydantic for External Data

All data from JSON configs or user input should go through Pydantic validation:

```python
# Good
config = AgentConfig.from_file(config_path)

# Bad
with open(config_path) as f:
    config = json.load(f)  # No validation!
```

### 2. Field Constraints

Use Pydantic's `Field()` for constraints:

```python
class TaskConfig(BaseModel):
    prompt: str = Field(..., min_length=1)  # Must be non-empty
    timeout: int = Field(default=30, gt=0)  # Must be positive
```

### 3. Custom Validators

Use `@field_validator` for complex validation:

```python
@field_validator('type')
@classmethod
def validate_type(cls, v: str) -> str:
    if v not in ["string", "bool", "int"]:
        raise ValueError(f"Invalid arg type: {v}")
    return v
```

### 4. Model Config

Configure model behavior with `model_config`:

```python
model_config = {
    "extra": "allow",      # Allow extra fields
    "strict": True,        # Strict type checking
    "frozen": True         # Immutable after creation
}
```

---

## Type Hierarchy

```
ComposableAgent System:
├── AgentConfig (Pydantic)
│   └── args: dict[str, ArgSpec (Pydantic)]
├── TaskConfig (Pydantic)
└── AgentResult (dataclass)

Orchestrator System:
├── ExecutionPlan (Pydantic)
│   └── tasks: list[AgentTask (Pydantic)]
└── OrchestratorResult (Pydantic)
    ├── plan: ExecutionPlan | None
    └── agent_results: list[dict]

Configuration:
└── PromptConfig (Pydantic)
    └── enabled_prompts: list[str]
```

---

## Common Patterns

### Loading and Validating Agent Configs

```python
from glyx_mcp.composable_agent import AgentConfig, AgentKey, ComposableAgent

# From file
config = AgentConfig.from_file("config/aider.json")

# From agent key (enum)
agent = ComposableAgent.from_key(AgentKey.AIDER)
```

### Executing with Validation

```python
from glyx_mcp.composable_agent import TaskConfig

# Pydantic validates on construction
task = TaskConfig(
    prompt="Add tests",
    files="src/main.py"
)

result = await agent.execute(task.model_dump(), timeout=300)
```

### Orchestration Flow

```python
from glyx_mcp.agents.orchestrator import Orchestrator, OrchestratorResult

orchestrator = Orchestrator()
result: OrchestratorResult = await orchestrator.orchestrate(
    "Refactor the auth module and add security tests"
)

# All types are validated
assert isinstance(result.plan, ExecutionPlan)
for task in result.plan.tasks:
    assert isinstance(task, AgentTask)
```

---

## Error Handling

### Validation Errors

```python
from pydantic import ValidationError

try:
    config = AgentConfig.from_file("invalid.json")
except ValidationError as e:
    print(f"Invalid config: {e}")
    # e.errors() gives detailed error info
```

### Runtime Errors

```python
from glyx_mcp.composable_agent import (
    AgentError,
    AgentTimeoutError,
    AgentExecutionError,
    AgentConfigError
)

try:
    result = await agent.execute(task_config)
except AgentTimeoutError:
    print("Agent timed out")
except AgentExecutionError:
    print("Agent execution failed")
except AgentConfigError:
    print("Invalid configuration")
```

---

## Testing with Pydantic Types

### Unit Tests

```python
def test_arg_spec_validation():
    # Valid
    spec = ArgSpec(flag="--model", type="string", required=True)

    # Invalid type
    with pytest.raises(ValidationError):
        ArgSpec(flag="--test", type="invalid")

def test_task_config_defaults():
    task = TaskConfig(prompt="Test")
    assert task.model == "gpt-5"  # Default value
```

### Mock Data

```python
from glyx_mcp.agents.orchestrator import AgentTask, ExecutionPlan

# Create test data
mock_plan = ExecutionPlan(
    reasoning="Test plan",
    tasks=[
        AgentTask(
            agent="aider",
            task_description="Test task",
            parameters={"prompt": "Test"}
        )
    ]
)
```

---

## Additional Resources

- [Pydantic Documentation](https://docs.pydantic.dev/)
- [CLAUDE.md](../CLAUDE.md) - Project guidelines
- [src/glyx_mcp/composable_agent.py](../src/glyx_mcp/composable_agent.py) - Core types
- [src/glyx_mcp/agents/orchestrator.py](../src/glyx_mcp/agents/orchestrator.py) - Orchestrator types
- [tests/test_config_validation.py](../tests/test_config_validation.py) - Validation tests

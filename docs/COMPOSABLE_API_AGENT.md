# Composable API Agent

Build and execute custom AI agent workflows via REST API with the same JSON structure as `agents/*.json` files.

## Overview

The Composable API Agent feature allows you to:
- **Create custom agents** dynamically via API calls
- **Store agent configurations** in the database (no file system access needed)
- **Execute workflows** with the same JSON structure as static agent files
- **Manage agent lifecycle** (CRUD operations) through REST endpoints

## API Endpoints

### List Workflows
```bash
GET /api/agent-workflows?user_id={user_id}
```

**Query Parameters:**
- `user_id` (optional): Filter by user ID (omit for global workflows)

**Response:**
```json
[
  {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "agent_key": "my_custom_agent",
    "command": "python",
    "args": {...},
    "description": "Custom Python script executor",
    "user_id": null,
    "created_at": "2025-12-04T14:30:00Z",
    "updated_at": "2025-12-04T14:30:00Z"
  }
]
```

### Create Workflow
```bash
POST /api/agent-workflows
Content-Type: application/json

{
  "agent_key": "my_custom_agent",
  "command": "python",
  "args": {
    "script": {
      "flag": "",
      "type": "string",
      "required": true,
      "description": "Python script to run"
    },
    "verbose": {
      "flag": "--verbose",
      "type": "bool",
      "required": false,
      "default": false
    }
  },
  "description": "Custom Python script executor",
  "capabilities": ["scripting", "automation"]
}
```

### Get Workflow
```bash
GET /api/agent-workflows/{workflow_id}
```

### Update Workflow
```bash
PATCH /api/agent-workflows/{workflow_id}
Content-Type: application/json

{
  "description": "Updated description",
  "capabilities": ["scripting", "automation", "testing"]
}
```

### Delete Workflow
```bash
DELETE /api/agent-workflows/{workflow_id}
```

### Execute Workflow
```bash
POST /api/agent-workflows/{workflow_id}/execute
Content-Type: application/json

{
  "task_config": {
    "script": "analyze.py",
    "verbose": true
  },
  "timeout": 300
}
```

**Response:**
```json
{
  "success": true,
  "stdout": "Analysis complete...",
  "stderr": "",
  "exit_code": 0,
  "execution_time": 2.5,
  "timed_out": false
}
```

## JSON Structure

Agent workflows use the same structure as `agents/*.json` files:

```json
{
  "agent_key": "unique_identifier",
  "command": "cli_command_to_execute",
  "args": {
    "arg_name": {
      "flag": "--flag-name",     // Empty string for positional args
      "type": "string",           // "string", "bool", or "int"
      "required": true,           // Is this argument required?
      "default": null,            // Default value (can be string, int, bool, or null)
      "description": "Help text"  // Human-readable description
    }
  },
  "description": "What this agent does",
  "version": ">=1.0.0",           // Optional version requirement
  "capabilities": ["tag1", "tag2"] // Optional capability tags
}
```

## Examples

### Example 1: Custom Python Script Executor

```bash
curl -X POST http://localhost:8080/api/agent-workflows \
  -H "Content-Type: application/json" \
  -d '{
    "agent_key": "python_executor",
    "command": "python",
    "args": {
      "script": {
        "flag": "",
        "type": "string",
        "required": true,
        "description": "Python script path"
      },
      "args": {
        "flag": "",
        "type": "string",
        "required": false,
        "description": "Script arguments"
      }
    },
    "description": "Execute Python scripts",
    "capabilities": ["scripting"]
  }'
```

### Example 2: Custom Git Helper

```bash
curl -X POST http://localhost:8080/api/agent-workflows \
  -H "Content-Type: application/json" \
  -d '{
    "agent_key": "git_helper",
    "command": "git",
    "args": {
      "operation": {
        "flag": "",
        "type": "string",
        "required": true,
        "description": "Git operation (status, diff, log, etc)"
      },
      "verbose": {
        "flag": "--verbose",
        "type": "bool",
        "required": false,
        "default": false
      }
    },
    "description": "Git operations helper",
    "capabilities": ["git", "version-control"]
  }'
```

### Example 3: Custom Test Runner

```bash
curl -X POST http://localhost:8080/api/agent-workflows \
  -H "Content-Type: application/json" \
  -d '{
    "agent_key": "test_runner",
    "command": "pytest",
    "args": {
      "path": {
        "flag": "",
        "type": "string",
        "required": true,
        "description": "Test path"
      },
      "verbose": {
        "flag": "-v",
        "type": "bool",
        "required": false,
        "default": true
      },
      "coverage": {
        "flag": "--cov",
        "type": "bool",
        "required": false,
        "default": false
      }
    },
    "description": "Run Python tests with pytest",
    "capabilities": ["testing"]
  }'
```

## Execution Example

After creating a workflow, execute it:

```bash
# 1. Create workflow (returns ID)
WORKFLOW_ID=$(curl -X POST http://localhost:8080/api/agent-workflows \
  -H "Content-Type: application/json" \
  -d '{...}' | jq -r '.id')

# 2. Execute workflow
curl -X POST "http://localhost:8080/api/agent-workflows/$WORKFLOW_ID/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "task_config": {
      "script": "my_script.py",
      "verbose": true
    },
    "timeout": 120
  }'
```

## SDK Usage

```python
from glyx_python_sdk import (
    AgentWorkflowCreate,
    save_workflow,
    get_workflow,
    list_workflows,
)

# Create workflow
workflow_create = AgentWorkflowCreate(
    agent_key="my_agent",
    command="python",
    args={
        "script": {
            "flag": "",
            "type": "string",
            "required": True,
            "description": "Script to run"
        }
    },
    description="Custom agent",
)

# Save to database
workflow = save_workflow(workflow_create)

# List all workflows
workflows = list_workflows()

# Get specific workflow
workflow = get_workflow(workflow.id)

# Execute via API (or convert to ComposableAgent)
agent = workflow.to_composable_agent()
result = await agent.execute({"script": "test.py"}, timeout=120)
```

## Storage

Workflows are stored in the `workflow_templates` table in Supabase with the following mapping:

| Model Field | DB Column | Type | Description |
|-------------|-----------|------|-------------|
| `id` | `id` | UUID | Primary key |
| `agent_key` | `template_key` | TEXT | Agent identifier |
| `command` | `name` | TEXT | CLI command |
| `args` | `config` | JSONB | Argument specifications |
| `description` | `description` | TEXT | Human-readable description |
| `user_id` | `user_id` | TEXT | User ID (NULL for global) |
| `version` | - | - | Not stored (kept in config) |
| `capabilities` | - | - | Not stored (kept in config) |

## Use Cases

1. **Dynamic Agent Creation**: Create agents on-the-fly without deploying files
2. **Multi-tenancy**: Users can create their own custom agents (user_id filter)
3. **Agent Marketplace**: Store and share custom agent configurations
4. **CI/CD Integration**: Programmatically create/update agents in pipelines
5. **UI-Driven Composition**: Build visual agent composers that store via API

## Security Considerations

- **Command Execution**: Workflows execute arbitrary CLI commands - validate thoroughly
- **User Isolation**: Use `user_id` to ensure users only access their own workflows
- **Timeout Limits**: Execution timeout capped at 600 seconds (10 minutes)
- **Input Validation**: All args validated against ArgSpec schema

## Next Steps

- Chain multiple workflows together (multi-agent pipelines)
- Add conditional execution (on_success, on_failure)
- Implement workflow versioning
- Add execution history tracking
- Support parallel agent execution

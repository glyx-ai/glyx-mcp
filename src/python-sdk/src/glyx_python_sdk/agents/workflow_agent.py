"""WorkflowAgent - Creates ComposableWorkflow configurations from user requests."""

import json

from agents import Agent

from glyx_python_sdk.composable_workflows import ComposableWorkflow

# Generate schema at module load time
WORKFLOW_SCHEMA = json.dumps(ComposableWorkflow.model_json_schema(), indent=2)

WORKFLOW_AGENT_INSTRUCTIONS = f"""You are a workflow designer that creates composable agent workflows.

Given a user description, generate a workflow configuration with stages and connections.

## JSON Schema

```json
{WORKFLOW_SCHEMA}
```

## Key Rules

1. **Stage IDs**: Use meaningful IDs like "planner-1", "coder-1", "reviewer-1", "tester-1"

2. **Positioning**: Layout stages from left to right:
   - Start at x=100, increment by 200 for each stage
   - Use y=200 as default vertical position
   - Vary y for parallel stages (e.g., y=100 and y=300)

3. **Base Agent**: Default to "glyx" for all agents

4. **Connections**: Link stages logically:
   - Use "on_complete" for normal flow
   - Use "on_approval" for review gates
   - Use "on_failure" for error handling

5. **System Prompts**: Add tailored prompts for each stage's responsibility

## Example Workflows

### Simple Code Review
- coder -> reviewer

### Full Development Pipeline
- planner -> coder -> reviewer -> tester -> documenter

### Parallel Review
- coder -> [reviewer, security-reviewer] (parallel) -> tester

## Output Requirements

1. Output a valid ComposableWorkflow JSON
2. Include meaningful names and descriptions
3. Position stages for clear visual layout
4. Connect all stages appropriately
5. Add system prompts that define each agent's behavior
"""


def create_workflow_agent(model: str = "gpt-5.1") -> Agent:
    """Create a WorkflowAgent that generates ComposableWorkflow configurations.

    The agent creates visual workflow configurations based on user descriptions,
    suitable for use in workflow builder UIs.

    Args:
        model: Model for the agent's reasoning

    Returns:
        Agent configured to create ComposableWorkflow configs

    Example:
        ```python
        from agents import Runner
        from glyx_python_sdk.agents.workflow_agent import create_workflow_agent

        agent = create_workflow_agent()
        result = await Runner.run(agent, "Create a code review workflow")
        workflow = result.final_output  # ComposableWorkflow
        ```
    """
    return Agent(
        name="WorkflowAgent",
        instructions=WORKFLOW_AGENT_INSTRUCTIONS,
        model=model,
        output_type=ComposableWorkflow,
    )

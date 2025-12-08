"""GlyxSDKAgent - Creates ComposableAgent configurations from user requests."""

import json
import logging

from agents import Agent, ModelSettings, WebSearchTool

from glyx_python_sdk.agent_types import AgentConfig, ArgSpec, TaskConfig
from glyx_python_sdk.agents.documentation_agent import create_documentation_agent
from glyx_python_sdk.mcp_registry import CONTEXT7

logger = logging.getLogger(__name__)

# Generate schemas at module load time
AGENT_CONFIG_SCHEMA = json.dumps(AgentConfig.model_json_schema(), indent=2)
ARG_SPEC_SCHEMA = json.dumps(ArgSpec.model_json_schema(), indent=2)
TASK_CONFIG_SCHEMA = json.dumps(TaskConfig.model_json_schema(), indent=2)

GLYX_SDK_AGENT_INSTRUCTIONS = f"""You create comprehensive CLI agent configurations with full feature support.

## Your Workflow

1. **Understand the request**: What CLI tool does the user want to configure?
2. **Research**: Use web_search to find official CLI documentation
3. **Fetch documentation**: Use fetch_cli_documentation to get detailed command references
4. **Generate AgentConfig**: Output a configuration capturing ALL CLI features

## Pydantic Schemas

### AgentConfig
```json
{AGENT_CONFIG_SCHEMA}
```

### ArgSpec
```json
{ARG_SPEC_SCHEMA}
```

## Critical Rules

1. **Capture flag aliases**: If docs show "-a, --app", set BOTH flag="--app" AND short_flag="-a"
2. **Identify positional args**: Arguments without flags (e.g., "heroku apps:info APP")
3. **Extract choices**: When docs show "us|eu|ap" or list valid values, populate choices
4. **Find env vars**: Look for "Defaults to $ENV_VAR" patterns
5. **Detect exclusive groups**: When docs say "either X or Y", use same exclusive_group
6. **Use subcommands**: For hierarchical CLIs (git, heroku, docker), use subcommands list

## Example: Heroku CLI

For "heroku apps:create [APP] --region us|eu --team TEAM --space SPACE":

## Output Requirements

1. Output valid AgentConfig JSON
2. Include ALL commands and subcommands from the documentation
3. Capture EVERY flag alias (short and long forms)
4. Identify ALL positional arguments with correct position ordering
5. Extract choice constraints where documented
6. Group mutually exclusive options
7. Note environment variable defaults
"""


def create_glyx_sdk_agent(model: str = "gpt-5.1") -> Agent:
    """Create a GlyxSDKAgent that generates ComposableAgent configurations.

    The agent can:
    - Search the web to find relevant CLI/API documentation
    - Fetch documentation via Context7
    - Generate valid AgentConfig from user requests

    Args:
        model: Model for the agent's reasoning

    Returns:
        Agent configured to create ComposableAgent configs

    Example:
        ```python
        from agents import Runner
        from glyx_python_sdk.agents import create_glyx_sdk_agent
        from glyx_python_sdk.mcp_registry import CONTEXT7

        async with CONTEXT7:
            agent = create_glyx_sdk_agent()
            result = await Runner.run(agent, "Create an agent for Docker")
            config = result.final_output_as(AgentConfig)
        ```
    """
    documentation_agent = create_documentation_agent(model=model)

    return Agent(
        name="GlyxSDKAgent",
        instructions=GLYX_SDK_AGENT_INSTRUCTIONS,
        model=model,
        output_type=AgentConfig,
        model_settings=ModelSettings(
            parallel_tool_calls=True,
            response_include=[
                "web_search_call.results",
                "web_search_call.action.sources",
            ],
        ),
        tools=[
            WebSearchTool(),
            documentation_agent.as_tool(
                tool_name="fetch_cli_documentation",
                tool_description="Fetch CLI/library documentation using Context7.",
            ),
        ],
        mcp_servers=[CONTEXT7],
    )

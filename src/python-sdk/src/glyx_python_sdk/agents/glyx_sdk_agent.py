"""GlyxSDKAgent - Expert on Glyx system with documentation handoff."""

import json
import logging

from agents import Agent, AgentOutputSchema
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

from glyx_python_sdk.agent import AgentConfig, ArgSpec, TaskConfig
from glyx_python_sdk.agents.documentation_agent import create_documentation_agent
from glyx_python_sdk.mcp_registry import CONTEXT7

logger = logging.getLogger(__name__)

# Generate schemas at module load time
AGENT_CONFIG_SCHEMA = json.dumps(AgentConfig.model_json_schema(), indent=2)
ARG_SPEC_SCHEMA = json.dumps(ArgSpec.model_json_schema(), indent=2)
TASK_CONFIG_SCHEMA = json.dumps(TaskConfig.model_json_schema(), indent=2)

GLYX_SYSTEM_INSTRUCTIONS = f"""{RECOMMENDED_PROMPT_PREFIX}

You are an expert on the Glyx AI orchestration system. Your primary task is to help users
convert CLI tool documentation into valid ComposableAgent configurations.

## Pydantic Schemas

### AgentConfig (main config for CLI agents)
```json
{AGENT_CONFIG_SCHEMA}
```

### ArgSpec (specification for each CLI argument)
```json
{ARG_SPEC_SCHEMA}
```

### TaskConfig (runtime task parameters)
```json
{TASK_CONFIG_SCHEMA}
```

## Workflow
1. When given a CLI tool name or URL, handoff to the DocumentationAgent to fetch docs
2. Analyze the returned documentation to extract CLI arguments
3. Generate a valid AgentConfig JSON following the schemas above

## Key Rules
- agent_key: lowercase, no spaces (e.g., "fastmcp", "cursor")
- flag: the CLI flag (e.g., "--port", "-p") or "" for positional args
- type: must be "string", "bool", or "int"
- capabilities: relevant tags like ["code-generation", "file-editing", "web-scraping"]
"""


def create_glyx_sdk_agent(model: str = "gpt-5.1") -> Agent:
    """Create a GlyxSDKAgent with handoff to DocumentationAgent.

    Args:
        model: Model for the agent's reasoning

    Returns:
        Agent configured to convert CLI docs to ComposableAgent configs

    Example:
        ```python
        from agents import Runner
        from glyx_python_sdk.agents import create_glyx_sdk_agent

        async with CONTEXT7:
            agent = create_glyx_sdk_agent()
            result = await Runner.run(agent, "Create an agent config for fastmcp CLI")
        ```
    """
    documentation_agent = create_documentation_agent(model=model)

    return Agent(
        name="GlyxSDKAgent",
        instructions=GLYX_SYSTEM_INSTRUCTIONS,
        model=model,
        output_type=AgentOutputSchema(AgentConfig, strict_json_schema=False),
        tools=[
            documentation_agent.as_tool(
                tool_name="fetch_cli_documentation",
                tool_description="Fetch CLI tool documentation using Context7. Returns documentation text.",
            )
        ],
        mcp_servers=[CONTEXT7],
    )

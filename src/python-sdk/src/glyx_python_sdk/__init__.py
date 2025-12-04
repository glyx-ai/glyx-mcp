"""Glyx Python SDK - AI orchestration framework."""

from glyx_python_sdk.agent import (
    AgentConfig,
    AgentError,
    AgentKey,
    AgentResult,
    ArgSpec,
    ComposableAgent,
    TaskConfig,
)
from glyx_python_sdk.memory import save_memory, search_memory
from glyx_python_sdk.models.cursor import (
    BaseCursorEvent,
    CursorAssistantEvent,
    CursorResultEvent,
    CursorSystemEvent,
    CursorThinkingEvent,
    CursorToolCallEvent,
    CursorUserEvent,
    parse_cursor_event,
)
from glyx_python_sdk.models.response import (
    BaseResponseEvent,
    StreamEventType,
    parse_response_event,
    summarize_tool_activity,
)
from glyx_python_sdk.models.task import Task
from glyx_python_sdk.orchestrator import GlyxOrchestrator
from glyx_python_sdk.pipelines import (
    AgentSequence,
    AgentSequenceCreate,
    AgentSequenceStatus,
    AgentSequenceUpdate,
    Artifact,
    ArtifactType,
    ActorType,
    ConversationEvent,
    Pipeline,
    Role,
    Stage,
    StageStatus,
    delete_agent_sequence,
    get_agent_sequence,
    list_agent_sequences,
    save_agent_sequence,
)
from glyx_python_sdk.prompts import build_task_prompt, get_orchestrator_instructions
from glyx_python_sdk.registry import discover_and_register_agents, make_agent_wrapper
from glyx_python_sdk.settings import Settings, settings
from glyx_python_sdk.supabase_loader import (
    delete_agent_from_supabase,
    list_agents_from_supabase,
    load_agents_from_supabase,
    row_to_agent_config,
    save_agent_to_supabase,
)
from glyx_python_sdk.types import TaskData
from glyx_python_sdk.workflows import (
    AgentWorkflowConfig,
    AgentWorkflowCreate,
    AgentWorkflowExecuteRequest,
    AgentWorkflowUpdate,
    delete_workflow,
    get_workflow,
    list_workflows,
    save_workflow,
)
from glyx_python_sdk.tools import (
    ask_user,
    create_agent,
    delete_agent,
    get_agent,
    get_session_messages,
    list_agents,
    list_sessions,
    orchestrate,
)

__version__ = "0.0.1"

__all__ = [
    # Core agent classes
    "ComposableAgent",
    "AgentConfig",
    "AgentKey",
    "AgentResult",
    "ArgSpec",
    "TaskConfig",
    "AgentError",
    # Orchestrator
    "GlyxOrchestrator",
    # Pipeline management
    "Pipeline",
    "AgentSequence",
    "AgentSequenceCreate",
    "AgentSequenceUpdate",
    "AgentSequenceStatus",
    "Stage",
    "StageStatus",
    "Role",
    "Artifact",
    "ArtifactType",
    "ActorType",
    "ConversationEvent",
    "get_agent_sequence",
    "list_agent_sequences",
    "save_agent_sequence",
    "delete_agent_sequence",
    # Memory functions
    "save_memory",
    "search_memory",
    # Types
    "TaskData",
    "Task",
    # Models
    "BaseCursorEvent",
    "CursorAssistantEvent",
    "CursorResultEvent",
    "CursorSystemEvent",
    "CursorThinkingEvent",
    "CursorToolCallEvent",
    "CursorUserEvent",
    "parse_cursor_event",
    "BaseResponseEvent",
    "StreamEventType",
    "parse_response_event",
    "summarize_tool_activity",
    # Registry
    "discover_and_register_agents",
    "make_agent_wrapper",
    # Settings
    "Settings",
    "settings",
    # Supabase loader
    "load_agents_from_supabase",
    "save_agent_to_supabase",
    "delete_agent_from_supabase",
    "list_agents_from_supabase",
    "row_to_agent_config",
    # Prompts
    "build_task_prompt",
    "get_orchestrator_instructions",
    # Workflows (Composable API Agent)
    "AgentWorkflowConfig",
    "AgentWorkflowCreate",
    "AgentWorkflowUpdate",
    "AgentWorkflowExecuteRequest",
    "get_workflow",
    "list_workflows",
    "save_workflow",
    "delete_workflow",
    # MCP Tools
    "ask_user",
    "create_agent",
    "delete_agent",
    "get_agent",
    "get_session_messages",
    "list_agents",
    "list_sessions",
    "orchestrate",
    # Version
    "__version__",
]

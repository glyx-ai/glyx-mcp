from enum import Enum
from pydantic import BaseModel


class EventType(str, Enum):
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    USER = "user"


class ActivityType(str, Enum):
    MESSAGE = "message"
    CODE = "code"
    REVIEW = "review"
    DEPLOYMENT = "deployment"
    ERROR = "error"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


EVENT_TO_ACTIVITY: dict[EventType, ActivityType] = {
    EventType.THINKING: ActivityType.THINKING,
    EventType.TOOL_CALL: ActivityType.TOOL_CALL,
    EventType.ASSISTANT: ActivityType.MESSAGE,
}


class ExecutionRequest(BaseModel):
    task_id: str
    prompt: str
    model: str = "gpt-5"
    langfuse_trace_id: str
    organization_id: str
    organization_name: str


class ExecutionResponse(BaseModel):
    status: str
    trace_id: str


class ActivityInsert(BaseModel):
    org_id: str
    org_name: str
    organization_id: str
    actor: str = "agent"
    type: ActivityType
    content: str
    role: str | None = None
    metadata: dict | None = None


class TaskUpdate(BaseModel):
    status: TaskStatus
    completed_at: str | None = None

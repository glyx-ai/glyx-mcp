"""Declarative stream item models for orchestrator output."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


class MessageItem(BaseModel):
    """Message output from the orchestrator."""

    type: Literal["message"] = "message"
    content: str

    @classmethod
    def from_raw(cls, raw_item: Any) -> MessageItem:
        """Extract text content from ResponseOutputMessage."""
        texts = [c.text for c in getattr(raw_item, "content", []) if hasattr(c, "text")]
        return cls(content=" ".join(texts))


class ToolCallItem(BaseModel):
    """Tool invocation by the orchestrator."""

    type: Literal["tool_call"] = "tool_call"
    name: str
    arguments: str

    @classmethod
    def from_raw(cls, raw_item: Any) -> ToolCallItem:
        """Extract tool call details."""
        return cls(
            name=getattr(raw_item, "name", "unknown"),
            arguments=getattr(raw_item, "arguments", "{}"),
        )


class ToolOutputItem(BaseModel):
    """Output from a tool execution."""

    type: Literal["tool_output"] = "tool_output"
    output: str

    @classmethod
    def from_output(cls, output: str) -> ToolOutputItem:
        """Create from tool output string."""
        return cls(output=output[:2000] if len(output) > 2000 else output)


class ReasoningItem(BaseModel):
    """Reasoning/thinking output from the model."""

    type: Literal["reasoning"] = "reasoning"
    content: str

    @classmethod
    def from_raw(cls, raw_item: Any) -> ReasoningItem:
        """Extract reasoning summary."""
        summary = getattr(raw_item, "summary", [])
        texts = [s.text for s in summary if hasattr(s, "text")]
        return cls(content=" ".join(texts)[:1000])


StreamItem = Annotated[
    Union[MessageItem, ToolCallItem, ToolOutputItem, ReasoningItem],
    Field(discriminator="type"),
]


def stream_item_from_agent(item: Any) -> BaseModel:
    """Convert an OpenAI agents SDK item to a StreamItem."""
    from agents.items import (
        MessageOutputItem,
        ReasoningItem as AgentReasoningItem,
        ToolCallItem as AgentToolCallItem,
        ToolCallOutputItem,
    )

    match item:
        case MessageOutputItem(raw_item=raw):
            return MessageItem.from_raw(raw)
        case AgentToolCallItem(raw_item=raw):
            return ToolCallItem.from_raw(raw)
        case ToolCallOutputItem(output=output):
            return ToolOutputItem.from_output(output)
        case AgentReasoningItem(raw_item=raw):
            return ReasoningItem.from_raw(raw)
        case _:
            return MessageItem(content=str(item)[:500])


def parse_stream_item(data: dict[str, Any]) -> MessageItem | ToolCallItem | ToolOutputItem | ReasoningItem:
    """Parse a streamed item dict back into a typed model."""
    item_type = data.get("type")
    match item_type:
        case "message":
            return MessageItem.model_validate(data)
        case "tool_call":
            return ToolCallItem.model_validate(data)
        case "tool_output":
            return ToolOutputItem.model_validate(data)
        case "reasoning":
            return ReasoningItem.model_validate(data)
        case _:
            return MessageItem(content=str(data))

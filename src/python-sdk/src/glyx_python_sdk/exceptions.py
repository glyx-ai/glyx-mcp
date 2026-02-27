"""Exceptions for glyx-python-sdk."""


class AgentError(Exception):
    """Base exception for agent errors."""

    pass


class AgentTimeoutError(AgentError):
    """Raised when agent execution times out."""

    pass


class AgentExecutionError(AgentError):
    """Raised when agent execution fails."""

    pass


class AgentConfigError(AgentError):
    """Raised when agent configuration is invalid."""

    pass

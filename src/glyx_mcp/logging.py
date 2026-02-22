"""Rich-based logging configuration for Glyx.

Provides beautiful, colored console output for local development with:
- Color-coded log levels (ERROR=red, WARNING=yellow, INFO=green, DEBUG=blue)
- Component prefixes with distinct colors
- Pretty-printed JSON payloads
- Auto-detection of TTY for production safety
"""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

if TYPE_CHECKING:
    pass

# Custom theme for Glyx components
GLYX_THEME = Theme({
    "logging.level.debug": "blue",
    "logging.level.info": "green",
    "logging.level.warning": "yellow",
    "logging.level.error": "red bold",
    "logging.level.critical": "red bold reverse",
    "mcp": "cyan bold",
    "daemon": "magenta bold",
    "agent": "yellow bold",
    "api": "blue bold",
    "auth": "green bold",
    "hitl": "red bold",
    "task": "cyan",
    "ws": "magenta",
})

# Component color mapping for log prefixes
COMPONENT_STYLES = {
    "MCP": "cyan bold",
    "DAEMON": "magenta bold",
    "AGENT": "yellow bold",
    "API": "blue bold",
    "AUTH": "green bold",
    "HITL": "red bold",
    "TASK": "cyan",
    "WS": "magenta",
    "DISPATCH": "yellow",
    "STREAM": "blue",
}


def is_tty() -> bool:
    """Check if stdout is a TTY (interactive terminal)."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def should_use_rich() -> bool:
    """Determine if Rich logging should be used.

    Returns True if:
    - GLYX_RICH_LOGS=1 is set (force enable)
    - Running in a TTY and GLYX_RICH_LOGS is not explicitly disabled
    """
    env_value = os.environ.get("GLYX_RICH_LOGS", "").lower()

    # Explicit enable/disable
    if env_value in ("1", "true", "yes"):
        return True
    if env_value in ("0", "false", "no"):
        return False

    # Auto-detect: use Rich in TTY, plain in production/docker
    return is_tty()


def configure_logging(
    level: int = logging.INFO,
    force_rich: bool | None = None,
) -> None:
    """Configure logging with Rich console handler.

    Args:
        level: Logging level (default: INFO)
        force_rich: Override auto-detection. None = auto-detect.
    """
    use_rich = force_rich if force_rich is not None else should_use_rich()

    # Remove existing handlers
    root = logging.getLogger()
    root.handlers.clear()

    if use_rich:
        # Rich console with custom theme
        console = Console(theme=GLYX_THEME, force_terminal=True)

        handler = RichHandler(
            console=console,
            show_time=True,
            show_level=True,
            show_path=False,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            markup=True,
            log_time_format="[%Y-%m-%d %H:%M:%S]",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        # Plain text format for production
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root.addHandler(handler)
    root.setLevel(level)

    # Silence noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


# Convenience function to format component prefixes with color
def format_component(component: str) -> str:
    """Format a component name with Rich markup.

    Usage in log messages:
        logger.info(f"{format_component('MCP')} Connected to server")

    Args:
        component: Component name (MCP, DAEMON, AGENT, etc.)

    Returns:
        Rich-formatted component string
    """
    style = COMPONENT_STYLES.get(component.upper(), "white")
    return f"[{style}][{component}][/{style}]"

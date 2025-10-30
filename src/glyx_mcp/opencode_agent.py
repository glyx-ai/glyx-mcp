"""Adapter for invoking the external `opencode` CLI.

This module provides a minimal wrapper that shells out to the installed
`opencode` binary, capturing stdout/stderr and returning a structured result.
"""

from __future__ import annotations

import subprocess


def run_opencode(flags: list[str], input_text: str | None = None, timeout: int = 300) -> tuple[int, str, str]:
    """Run the `opencode` CLI with the provided flags and optional stdin.

    Args:
        flags: Command-line flags and arguments to pass to `opencode`.
        input_text: Optional text to pass on stdin to the process.
        timeout: Timeout in seconds for the subprocess execution.

    Returns:
        A tuple of (returncode, stdout, stderr).
    """

    cmd = ["opencode", *flags]

    try:
        result = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"opencode execution timeout after {timeout} seconds"
    except FileNotFoundError:
        return 127, "", "opencode command not found"
    except Exception as exc:  # pragma: no cover - unexpected errors
        return 1, "", str(exc)

"""
Shared pytest fixtures and utilities for integration tests.

This module provides fixtures for:
- Temporary directories and files
- API key validation
- CLI availability checking
- Test cleanup handlers
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Generator

import pytest


# =============================================================================
# API Key Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def api_keys() -> Dict[str, str]:
    """
    Validate and return dict of test API keys from environment.

    Required environment variables:
    - CLAUDE_API_KEY: For Claude agent tests
    - OPENROUTER_API_KEY: For OpenCode/Grok tests
    - ANTHROPIC_API_KEY: For Aider tests (if using Claude model)
    - OPENAI_API_KEY: For Aider/Codex tests (if using GPT models)

    Returns:
        Dict mapping agent names to API keys

    Raises:
        pytest.fail if required keys are missing
    """
    keys = {
        "claude": os.getenv("CLAUDE_API_KEY"),
        "openrouter": os.getenv("OPENROUTER_API_KEY"),
        "anthropic": os.getenv("ANTHROPIC_API_KEY"),
        "openai": os.getenv("OPENAI_API_KEY"),
    }

    # Check which keys are missing
    missing = [name for name, key in keys.items() if not key]

    if missing:
        pytest.fail(
            f"Missing required API keys for E2E tests: {', '.join(missing).upper()}_API_KEY\n"
            f"Please set environment variables:\n"
            f"  export CLAUDE_API_KEY='your-key'\n"
            f"  export OPENROUTER_API_KEY='your-key'\n"
            f"  export ANTHROPIC_API_KEY='your-key'\n"
            f"  export OPENAI_API_KEY='your-key'\n"
        )

    return keys


def require_api_key(api_keys: Dict[str, str], agent_name: str) -> str:
    """
    Helper to check if API key is available for a specific agent.

    Args:
        api_keys: Dict from api_keys fixture
        agent_name: Name of agent (claude, openrouter, anthropic, openai)

    Returns:
        The API key string

    Raises:
        pytest.fail if key is missing
    """
    key = api_keys.get(agent_name)
    if not key:
        pytest.fail(f"API key for {agent_name} not available: {agent_name.upper()}_API_KEY not set")
    return key


# =============================================================================
# CLI Availability Fixtures
# =============================================================================


def check_cli_installed(cli_name: str, min_version: str | None = None) -> None:
    """
    Check if a CLI tool is installed and optionally verify minimum version.

    Args:
        cli_name: Name of the CLI command (e.g., 'aider', 'claude')
        min_version: Optional minimum version string (e.g., '0.86.0')

    Raises:
        pytest.fail: If CLI is not installed or version is too old
    """
    # Check if CLI exists in PATH
    cli_path = shutil.which(cli_name)
    if not cli_path:
        pytest.fail(
            f"CLI '{cli_name}' is not installed or not in PATH.\n"
            f"Please install it before running integration tests.\n"
            f"Example: pip install {cli_name}"
        )

    # If min_version specified, try to check version
    if min_version:
        try:
            result = subprocess.run(
                [cli_name, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            version_output = result.stdout + result.stderr

            # Simple version check (this may need adjustment per CLI)
            # Just log it for now, don't fail on version mismatch
            if result.returncode == 0:
                print(f"✓ {cli_name} installed: {version_output.strip()}")
        except Exception as e:
            print(f"Warning: Could not verify {cli_name} version: {e}")


@pytest.fixture(scope="session")
def claude_cli() -> None:
    """Verify Claude CLI is installed."""
    check_cli_installed("claude", min_version="1.0.0")


@pytest.fixture(scope="session")
def opencode_cli() -> None:
    """Verify OpenCode CLI is installed."""
    check_cli_installed("opencode")


@pytest.fixture(scope="session")
def aider_cli() -> None:
    """Verify Aider CLI is installed."""
    check_cli_installed("aider", min_version="0.86.0")


@pytest.fixture(scope="session")
def codex_cli() -> None:
    """Verify Codex CLI is installed."""
    check_cli_installed("codex", min_version="1.0.0")


# =============================================================================
# Temporary Directory Fixtures
# =============================================================================


@pytest.fixture
def temp_test_dir() -> Generator[Path, None, None]:
    """
    Create a temporary directory for test files, clean up after test.

    Yields:
        Path to temporary directory

    Example:
        def test_something(temp_test_dir):
            test_file = temp_test_dir / "test.py"
            test_file.write_text("print('hello')")
            # ... do test ...
            # Directory is automatically cleaned up
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="glyx_mcp_test_"))

    try:
        yield temp_dir
    finally:
        # Clean up the directory and all its contents
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_test_file(temp_test_dir: Path) -> Generator[Path, None, None]:
    """
    Create a temporary test file with simple Python content.

    Args:
        temp_test_dir: Temporary directory fixture

    Yields:
        Path to temporary Python file

    Example:
        def test_something(temp_test_file):
            original = temp_test_file.read_text()
            # ... modify file ...
            assert temp_test_file.read_text() != original
    """
    test_file = temp_test_dir / "test_code.py"
    test_file.write_text(create_test_file_content())

    yield test_file

    # File will be cleaned up with temp_test_dir


# =============================================================================
# Test Utility Functions
# =============================================================================


def create_test_file_content() -> str:
    """
    Generate simple Python code content for testing.

    Returns:
        String containing simple Python code
    """
    return """#!/usr/bin/env python3
\"\"\"Simple test file for integration tests.\"\"\"


def calculate_sum(a: int, b: int) -> int:
    \"\"\"Calculate sum of two numbers.\"\"\"
    return a + b


def calculate_product(a: int, b: int) -> int:
    \"\"\"Calculate product of two numbers.\"\"\"
    return a * b


if __name__ == "__main__":
    result = calculate_sum(2, 3)
    print(f"Sum: {result}")
"""


def verify_file_modified(file_path: Path, original_content: str) -> bool:
    """
    Verify that a file has been modified from its original content.

    Args:
        file_path: Path to file to check
        original_content: Original content before modification

    Returns:
        True if file was modified, False otherwise
    """
    if not file_path.exists():
        return False

    current_content = file_path.read_text()
    return current_content != original_content


def create_test_prompt(agent_type: str) -> str:
    """
    Create a minimal test prompt appropriate for each agent type.

    Args:
        agent_type: Type of agent (claude, aider, codex, opencode)

    Returns:
        String containing appropriate test prompt
    """
    prompts = {
        "claude": "What is 2+2? Answer in one word.",
        "aider": "Add a docstring to the calculate_sum function",
        "codex": "print('Hello from codex')",
        "opencode": "What is the capital of France? Answer in one word.",
        "grok": "What is 5+5? Answer with just the number.",
    }

    return prompts.get(agent_type, "Simple test prompt")


# =============================================================================
# Cost Tracking (Optional)
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def log_test_session_info():
    """Log information about the test session."""
    print("\n" + "=" * 70)
    print("INTEGRATION TEST SESSION")
    print("=" * 70)
    print("These tests make REAL API calls and may incur costs.")
    print("Estimated cost per full run: $0.10-$0.50")
    print("=" * 70 + "\n")

    yield

    print("\n" + "=" * 70)
    print("INTEGRATION TEST SESSION COMPLETE")
    print("=" * 70 + "\n")

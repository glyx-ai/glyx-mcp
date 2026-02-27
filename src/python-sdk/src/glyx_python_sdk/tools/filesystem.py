"""Filesystem tools for agents."""

import os
from agents import function_tool

# It's important to define the project root to prevent the agent
# from accessing files outside the project directory.
# This should be set to a secure, well-defined location.
PROJECT_ROOT = os.path.abspath(os.environ.get("PROJECT_ROOT", "."))


def is_safe_path(path: str) -> bool:
    """Check if the path is within the project root."""
    abs_path = os.path.abspath(os.path.join(PROJECT_ROOT, path))
    return os.path.commonpath([abs_path, PROJECT_ROOT]) == PROJECT_ROOT


@function_tool
def read_file(file_path: str) -> str:
    """
    Reads the content of a file.

    Args:
        file_path: The path to the file relative to the project root.

    Returns:
        The content of the file, or an error message if the file cannot be read.
    """
    if not is_safe_path(file_path):
        return f"Error: Path '{file_path}' is outside the allowed project directory."

    try:
        with open(os.path.join(PROJECT_ROOT, file_path), "r") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"


@function_tool
def write_file(file_path: str, content: str) -> str:
    """
    Writes content to a file.

    Args:
        file_path: The path to the file relative to the project root.
        content: The content to write to the file.

    Returns:
        A success message, or an error message if the file cannot be written.
    """
    if not is_safe_path(file_path):
        return f"Error: Path '{file_path}' is outside the allowed project directory."

    try:
        with open(os.path.join(PROJECT_ROOT, file_path), "w") as f:
            f.write(content)
        return f"Successfully wrote to {file_path}"
    except Exception as e:
        return f"Error writing file: {e}"


@function_tool
def list_directory(path: str) -> str:
    """
    Lists the contents of a directory.

    Args:
        path: The path to the directory relative to the project root.

    Returns:
        A list of files and directories, or an error message.
    """
    if not is_safe_path(path):
        return f"Error: Path '{path}' is outside the allowed project directory."

    try:
        return "\n".join(os.listdir(os.path.join(PROJECT_ROOT, path)))
    except Exception as e:
        return f"Error listing directory: {e}"

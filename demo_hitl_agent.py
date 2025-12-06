"""
Human-in-the-Loop Demo Agent using Pydantic AI SDK.

This demonstrates the deferred tools pattern for requiring human approval
before executing sensitive operations.
"""

from pydantic_ai import (
    Agent,
    ApprovalRequired,
    DeferredToolRequests,
    DeferredToolResults,
    RunContext,
    ToolDenied,
)

# Define agent with DeferredToolRequests as possible output type
agent = Agent(
    "openai:gpt-4o",
    output_type=[str, DeferredToolRequests],
    system_prompt="You are a helpful assistant that can manage files and user accounts.",
)

PROTECTED_FILES = {".env", "secrets.yaml", "credentials.json"}


@agent.tool
def update_file(ctx: RunContext, path: str, content: str) -> str:
    """Update a file with new content."""
    # Conditionally require approval for protected files
    if path in PROTECTED_FILES and not ctx.tool_call_approved:
        raise ApprovalRequired(metadata={"reason": "protected file", "path": path})
    return f"File '{path}' updated with content: {content[:50]}..."


@agent.tool_plain(requires_approval=True)
def delete_file(path: str) -> str:
    """Delete a file from the filesystem."""
    return f"File '{path}' deleted successfully"


@agent.tool_plain(requires_approval=True)
def delete_user(user_id: int) -> str:
    """Delete a user account from the system."""
    return f"User {user_id} deleted successfully"


@agent.tool_plain
def list_files(directory: str) -> str:
    """List files in a directory (no approval needed)."""
    return f"Files in '{directory}': config.yaml, main.py, README.md"


def get_human_approval(tool_name: str, args: dict, metadata: dict | None = None) -> bool | ToolDenied:
    """Interactive prompt for human approval."""
    print("\n" + "=" * 60)
    print("APPROVAL REQUIRED")
    print("=" * 60)
    print(f"Tool: {tool_name}")
    print(f"Arguments: {args}")
    if metadata:
        print(f"Metadata: {metadata}")
    print("-" * 60)

    response = input("Approve this action? [y/n/reason to deny]: ").strip().lower()

    if response == "y":
        return True
    elif response == "n":
        return ToolDenied("Action denied by user")
    else:
        return ToolDenied(f"Action denied: {response}")


def run_with_approval(prompt: str) -> str:
    """Run agent with human-in-the-loop approval flow."""
    print(f"\nUser prompt: {prompt}")
    print("-" * 60)

    # First run - may return deferred tool requests
    result = agent.run_sync(prompt)
    messages = result.all_messages()

    # Check if we got deferred requests needing approval
    if isinstance(result.output, DeferredToolRequests):
        requests = result.output
        print(f"\nAgent requested {len(requests.approvals)} tool(s) requiring approval:")

        # Collect approvals for each deferred tool call
        results = DeferredToolResults()

        for call in requests.approvals:
            approval = get_human_approval(
                tool_name=call.tool_name,
                args=call.args_as_dict(),
                metadata=getattr(call, "metadata", None),
            )
            results.approvals[call.tool_call_id] = approval

        # Continue agent run with approval decisions
        result = agent.run_sync(
            message_history=messages,
            deferred_tool_results=results,
        )

    return result.output


def main():
    """Demo the human-in-the-loop agent."""
    print("\n" + "=" * 60)
    print("HUMAN-IN-THE-LOOP AGENT DEMO")
    print("=" * 60)

    # Demo 1: Action requiring approval (delete)
    print("\n--- Demo 1: Delete operation (always requires approval) ---")
    output = run_with_approval("Delete the file called 'old_config.yaml'")
    print(f"\nFinal output: {output}")

    # Demo 2: Protected file update
    print("\n--- Demo 2: Protected file update ---")
    output = run_with_approval("Update the .env file with 'API_KEY=secret123'")
    print(f"\nFinal output: {output}")

    # Demo 3: Non-protected action (no approval needed)
    print("\n--- Demo 3: Safe operation (no approval needed) ---")
    output = run_with_approval("List the files in the /home directory")
    print(f"\nFinal output: {output}")

    # Demo 4: Multiple actions
    print("\n--- Demo 4: Multiple actions ---")
    output = run_with_approval("Delete user 42, update README.md with 'Hello World', and delete temp.txt")
    print(f"\nFinal output: {output}")


if __name__ == "__main__":
    main()

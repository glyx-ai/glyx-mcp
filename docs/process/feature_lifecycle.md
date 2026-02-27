# Feature Lifecycle Process

This document outlines the standard process for developing new features for the Glyx MCP server, utilizing our automated **Feature Management Framework**.

## Overview

The lifecycle of a feature follows these stages:
1.  **Planning**: Defining the problem and solution.
2.  **Implementation**: Writing the code.
3.  **Verification**: Ensuring correctness.
4.  **Documentation**: Updating artifacts and user guides.

We use **Linear** for issue tracking and **implementation_plan.md** / **walkthrough.md** artifacts to document decision-making.

## CLI Tools

We have a built-in CLI to automate parts of this process:

```bash
# Start a new feature (Creates Linear Issue + Notification)
python -m src.framework.cli start "Feature Name"

# Generate a Plan Template
python -m src.framework.cli plan "Feature Name"
```

## Detailed Workflow

### 1. Start (Planning)
*   **Action**: `python -m src.framework.cli start "My Feature"`
*   **Result**:
    *   A Linear Issue is created in the backlog.
    *   A notification is sent to the team via Knock.
*   **Next Step**: Create an `implementation_plan.md` using the generator.

### 2. Design (Planning)
*   **Action**: `python -m src.framework.cli plan "My Feature"`
*   **Result**: Creates `implementation_plan.md` in your CWD.
*   **Task**: Fill out the plan.
    *   Define **Goals**.
    *   Identify **User Review** items.
    *   List **Proposed Changes**.
    *   Define **Verification Plan**.
    *   *Agent Tip*: Ask the AI Agent to "Create an implementation plan for X" and it will use this format.

### 3. Implementation (Execution)
*   Write code according to the plan.
*   Update `task.md` (if using one) to track progress.

### 4. Verification
*   Run tests.
*   Create a `walkthrough.md` artifact (or update the existing one) to demonstrate the feature works.
*   Include screenshots or CLI outputs.

### 5. Completion
*   Close the Linear issue (currently manual, or via Agent).
*   Merge code.

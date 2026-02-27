import json
from glyx_python_sdk.composable_workflows import (
    ComposableWorkflow,
    WorkflowStage,
    WorkflowConnection,
    AgentInstance,
    Position,
)


def create_feature_implementation_workflow():
    """Creates a ComposableWorkflow for a feature implementation process."""

    # 1. Define the Stages
    researcher_stage = WorkflowStage(
        id="researcher-1",
        name="Research Agent",
        position=Position(x=100, y=200),
        agent=AgentInstance(
            id="researcher-agent",
            system_prompt=(
                "You are a research agent. Your task is to analyze a feature request, "
                "research the existing codebase, and create a detailed implementation plan. "
                "The plan should be clear and provide enough detail for an implementation "
                "agent to execute it."
            ),
        ),
    )

    implementer_stage = WorkflowStage(
        id="implementer-1",
        name="Implementation Agent",
        position=Position(x=300, y=200),
        agent=AgentInstance(
            id="implementer-agent",
            system_prompt=(
                "You are a senior software engineer specializing in FastAPI, Next.js, "
                "Supabase, and ShadCN. You will be given a detailed implementation "
                "plan. Your task is to implement the feature as described in the plan, "
                "writing clean, efficient, and well-documented code."
            ),
        ),
    )

    code_reviewer_stage = WorkflowStage(
        id="code-reviewer-1",
        name="Code Review Agent",
        position=Position(x=500, y=100),
        agent=AgentInstance(
            id="code-reviewer-agent",
            system_prompt=(
                "You are a code quality review agent. You will be given code for a new "
                "feature. Your task is to review the code for quality, correctness, "
                "performance, and adherence to project standards. Provide feedback for "
                "revisions if necessary."
            ),
        ),
    )

    qa_reviewer_stage = WorkflowStage(
        id="qa-reviewer-1",
        name="Visual QA Agent",
        position=Position(x=500, y=300),
        agent=AgentInstance(
            id="qa-reviewer-agent",
            system_prompt=(
                "You are a QA agent with a focus on product and visual quality. You will "
                "be given a newly implemented feature. Your task is to review the "
                "feature from a user's perspective, checking for usability, visual "
                "consistency, and overall user experience. Report any bugs or visual glitches."
            ),
        ),
    )

    final_review_stage = WorkflowStage(
        id="final-review-1",
        name="Final Review",
        position=Position(x=700, y=200),
        agent=AgentInstance(
            id="final-review-agent",
            system_prompt=(
                "You are the final reviewer. You will receive the implementation and the "
                "feedback from the code and QA reviewers. Your task is to give the final "
                "approval or send it back for revisions."
            ),
        ),
    )

    # 2. Define the Connections
    connections = [
        WorkflowConnection(id="research-to-implement", source_stage_id="researcher-1", target_stage_id="implementer-1"),
        WorkflowConnection(
            id="implement-to-code-review", source_stage_id="implementer-1", target_stage_id="code-reviewer-1"
        ),
        WorkflowConnection(
            id="implement-to-qa-review", source_stage_id="implementer-1", target_stage_id="qa-reviewer-1"
        ),
        WorkflowConnection(
            id="code-review-to-final-review", source_stage_id="code-reviewer-1", target_stage_id="final-review-1"
        ),
        WorkflowConnection(
            id="qa-review-to-final-review", source_stage_id="qa-reviewer-1", target_stage_id="final-review-1"
        ),
    ]

    # 3. Create the ComposableWorkflow
    workflow = ComposableWorkflow(
        name="Feature Implementation Workflow",
        description=(
            "A multi-stage workflow for implementing new features, including research, "
            "implementation, code review, and QA."
        ),
        stages=[researcher_stage, implementer_stage, code_reviewer_stage, qa_reviewer_stage, final_review_stage],
        connections=connections,
    )

    return workflow


if __name__ == "__main__":
    workflow = create_feature_implementation_workflow()

    # Save the workflow to a JSON file
    file_path = "feature_implementation_workflow.json"
    with open(file_path, "w") as f:
        json.dump(workflow.model_dump(), f, indent=2)

    print(f"Workflow saved to {file_path}")

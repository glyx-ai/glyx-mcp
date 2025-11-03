"""Claude Code integration models and utilities.

This module provides Pydantic models for interacting with Claude Code's AskUserQuestion tool,
which allows structured user interaction with multiple-choice options.

Reference: https://docs.claude.com/
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class Option(BaseModel):
    """A single option in a question.

    Attributes:
        label: Display text (1-5 words, concise)
        description: Explanation of what this option means or what will happen if chosen
    """

    label: str = Field(
        ...,
        description="Display text for this option (1-5 words, concise)",
        min_length=1,
    )
    description: str = Field(
        ...,
        description="Explanation of what this option means or what will happen if chosen",
        min_length=1,
    )

    @field_validator("label")
    @classmethod
    def validate_label_length(cls, v: str) -> str:
        """Ensure label is concise (1-5 words)."""
        word_count = len(v.split())
        if word_count > 5:
            raise ValueError(f"Label must be 1-5 words, got {word_count} words")
        return v


class Question(BaseModel):
    """A question to ask the user with multiple-choice options.

    Attributes:
        question: The complete question (should end with '?')
        header: Very short label displayed as a chip/tag (max 12 chars)
        multiSelect: Whether to allow multiple selections
        options: Available choices (2-4 options)
    """

    question: str = Field(
        ...,
        description="Complete question to ask (should be clear, specific, and end with '?')",
        min_length=1,
    )
    header: str = Field(
        ...,
        description="Very short label displayed as a chip/tag (max 12 chars)",
        min_length=1,
        max_length=12,
    )
    multiSelect: bool = Field(
        ...,
        description="Allow multiple selections (use when choices are not mutually exclusive)",
    )
    options: List[Option] = Field(
        ...,
        description="Available choices (2-4 options). 'Other' option is automatically added.",
        min_length=2,
        max_length=4,
    )

    @field_validator("question")
    @classmethod
    def validate_question_ends_with_question_mark(cls, v: str) -> str:
        """Ensure question ends with a question mark."""
        if not v.strip().endswith("?"):
            raise ValueError("Question should end with a question mark")
        return v


class AskUserQuestionTool(BaseModel):
    """Claude Code AskUserQuestion tool for structured user interaction.

    This tool allows asking users questions with structured multiple-choice options.
    Users will always be able to select "Other" to provide custom text input.

    Technical Constraints:
    - 1-4 questions per call
    - 2-4 options per question
    - Header: max 12 characters
    - Option label: 1-5 words
    - "Other" option automatically added (don't include it)
    - multiSelect must be specified (not optional)

    Use Cases:
    1. Gather user preferences or requirements
    2. Clarify ambiguous instructions
    3. Get decisions on implementation choices during work
    4. Offer choices to the user about what direction to take

    Attributes:
        questions: Questions to ask (1-4 questions)
        answers: User answers collected (optional, populated after user responds)
    """

    questions: List[Question] = Field(
        ...,
        description="Questions to ask the user (1-4 questions)",
        min_length=1,
        max_length=4,
    )
    answers: Optional[Dict[str, str]] = Field(
        None,
        description="User answers collected by the permission component",
    )

    def to_claude_code_format(self) -> str:
        """Format as Claude Code-compatible string with [ASK_USER_QUESTION] markers.

        This format is designed to be detected and parsed by Claude Code when returned
        from an orchestrator or agent that doesn't have direct access to the
        AskUserQuestion tool.

        Returns:
            Formatted string with JSON structure wrapped in markers
        """
        import json

        json_str = json.dumps(self.model_dump(exclude={"answers"}, exclude_none=True), indent=2)
        return f"[ASK_USER_QUESTION]\n{json_str}\n[/ASK_USER_QUESTION]"

    @classmethod
    def from_simple_question(
        cls,
        question: str,
        header: str,
        options: List[tuple[str, str]],
        multi_select: bool = False,
    ) -> AskUserQuestionTool:
        """Create an AskUserQuestionTool from a simple question.

        Convenience method for creating a single question with options.

        Args:
            question: The question to ask (should end with '?')
            header: Short label (max 12 chars)
            options: List of (label, description) tuples (2-4 options)
            multi_select: Whether to allow multiple selections

        Returns:
            AskUserQuestionTool instance

        Example:
            >>> tool = AskUserQuestionTool.from_simple_question(
            ...     question="Which library should we use for date formatting?",
            ...     header="Library",
            ...     options=[
            ...         ("date-fns", "Modern JavaScript date utility library"),
            ...         ("moment.js", "Classic date manipulation library"),
            ...         ("dayjs", "Lightweight alternative to moment.js"),
            ...     ],
            ...     multi_select=False,
            ... )
        """
        return cls(
            questions=[
                Question(
                    question=question,
                    header=header,
                    multiSelect=multi_select,
                    options=[Option(label=label, description=desc) for label, desc in options],
                )
            ]
        )


def parse_ask_user_question_from_text(text: str) -> Optional[AskUserQuestionTool]:
    """Parse AskUserQuestionTool from text containing [ASK_USER_QUESTION] markers.

    This function extracts and parses the JSON structure from text that contains
    the [ASK_USER_QUESTION]...[/ASK_USER_QUESTION] markers.

    Args:
        text: Text containing the marked JSON structure

    Returns:
        Parsed AskUserQuestionTool instance, or None if markers not found

    Example:
        >>> text = '''
        ... I need more information.
        ... [ASK_USER_QUESTION]
        ... {"questions": [...]}
        ... [/ASK_USER_QUESTION]
        ... '''
        >>> tool = parse_ask_user_question_from_text(text)
    """
    import json
    import re

    # Extract JSON between markers
    pattern = r"\[ASK_USER_QUESTION\]\s*(.*?)\s*\[/ASK_USER_QUESTION\]"
    match = re.search(pattern, text, re.DOTALL)

    if not match:
        return None

    json_str = match.group(1).strip()

    try:
        data = json.loads(json_str)
        return AskUserQuestionTool.model_validate(data)
    except (json.JSONDecodeError, ValueError):
        return None

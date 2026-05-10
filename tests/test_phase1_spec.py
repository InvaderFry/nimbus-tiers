"""Tests guarding the canonical Phase 1 spec template."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "templates" / "PHASE1_SPEC.md"


def _extract_worked_example(text: str) -> str:
    """Return the body of the first fenced code block under the Worked example heading."""
    heading_idx = text.index("## Worked example: a well-formed step file")
    after_heading = text[heading_idx:]
    match = re.search(r"```[a-zA-Z]*\n(.*?)\n```", after_heading, flags=re.DOTALL)
    assert match is not None, "Worked example fenced code block not found"
    return match.group(1)


def test_worked_example_under_word_cap() -> None:
    """The worked example must respect the 300-word target it teaches.

    PHASE1_SPEC.md instructs planners to keep step files under ~300 words
    (the 400-token cap). If the in-doc example drifts above that, the spec
    contradicts itself.
    """
    body = _extract_worked_example(SPEC_PATH.read_text(encoding="utf-8"))
    word_count = len(body.split())
    assert word_count <= 300, (
        f"Worked example in PHASE1_SPEC.md is {word_count} words — must be ≤ 300 "
        "to match the cap the spec teaches."
    )


def test_worked_example_uses_required_step_structure() -> None:
    """The worked example must include each required section header."""
    body = _extract_worked_example(SPEC_PATH.read_text(encoding="utf-8"))
    for required in ("## Goal", "## Inspect first", "## Files to change",
                     "## Work", "## Acceptance tests", "## Done condition"):
        assert required in body, f"Worked example missing section: {required}"

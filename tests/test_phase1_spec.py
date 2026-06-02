"""Tests guarding the canonical Phase 1 spec template."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "templates" / "PHASE1_SPEC.md"


def _extract_worked_example_blocks(text: str) -> list[str]:
    """Return bodies of all fenced code blocks under the Worked example heading."""
    heading_idx = text.index("## Worked example:")
    after_heading = text[heading_idx:]
    blocks = re.findall(r"```[a-zA-Z]*\n(.*?)\n```", after_heading, flags=re.DOTALL)
    assert blocks, "Worked example fenced code block not found"
    return blocks


def test_worked_example_under_word_cap() -> None:
    """Each step in the worked example must respect the 300-word target it teaches.

    PHASE1_SPEC.md instructs planners to keep step files under ~300 words
    (the 400-token cap). If any in-doc example step drifts above that, the spec
    contradicts itself.
    """
    blocks = _extract_worked_example_blocks(SPEC_PATH.read_text(encoding="utf-8"))
    for i, block in enumerate(blocks, start=1):
        word_count = len(block.split())
        assert word_count <= 300, (
            f"Worked example step {i} in PHASE1_SPEC.md is {word_count} words — must be ≤ 300 "
            "to match the cap the spec teaches."
        )


def test_worked_example_uses_required_step_structure() -> None:
    """Across the worked example step pair, every required section header must appear."""
    blocks = _extract_worked_example_blocks(SPEC_PATH.read_text(encoding="utf-8"))
    combined = "\n".join(blocks)
    for required in ("## Goal", "## Inspect first", "## Files to change",
                     "## Work", "## Acceptance tests", "## Done condition"):
        assert required in combined, f"Worked example missing section: {required}"

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


def test_wiring_rule_rejects_test_slices() -> None:
    """The §5 wiring rule must say a framework test slice does not satisfy it.

    A slice (@RestClientTest, @WebMvcTest, …) loads a restricted, partly-mocked
    context and will not instantiate the real collaborator beans — so it cannot
    catch a missing/mismatched bean. The rule must direct planners to a
    full-context test (@SpringBootTest) instead. Regressing this reopens the
    exact gap that let a WebClient-vs-RestClient mismatch ship green.
    """
    text = SPEC_PATH.read_text(encoding="utf-8")
    for token in ("slice", "@RestClientTest", "@SpringBootTest", "full application context"):
        assert token in text, f"Wiring rule missing slice-vs-context-load token: {token}"


def test_java_http_client_consistency_guardrail_present() -> None:
    """The Java guardrails must cover HTTP-client / dependency consistency.

    The canonical local-model failure mixes a reactive client with the servlet
    starter (WebClient configured via RestClient-only requestFactory(...), or a
    WebClient service tested with @RestClientTest). The spec must name this so a
    planner ties the client to the declared starter.
    """
    text = SPEC_PATH.read_text(encoding="utf-8")
    for token in ("HTTP-client", "WebClient", "webflux", "requestFactory",
                  "spring-boot-starter-web"):
        assert token in text, f"HTTP-client consistency guardrail missing token: {token}"


def test_verify_sh_requires_exit_propagation_and_static_guards() -> None:
    """§4 must require exit-status propagation and allow cheap static defect guards.

    The lesson from the field failure: a gate that swallows a non-zero build
    status reports "tests passed" on code that does not compile. The spec must
    require propagating the real status and permit a fast grep-based backstop.
    """
    text = SPEC_PATH.read_text(encoding="utf-8")
    for token in ("PIPESTATUS", "exit status", "Static defect guards"):
        assert token in text, f"verify.sh section missing gate-hardening token: {token}"

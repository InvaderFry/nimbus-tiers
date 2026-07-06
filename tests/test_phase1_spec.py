"""Tests guarding the canonical Phase 1 spec template."""

from __future__ import annotations

import re

from nimbus_tiers.resources import templates_root

SPEC_PATH = templates_root() / "PHASE1_SPEC.md"


def _extract_worked_example_blocks(text: str) -> list[str]:
    """Return bodies of all fenced code blocks under the Worked example heading."""
    heading_idx = text.index("## Worked example:")
    after_heading = text[heading_idx:]
    blocks = re.findall(r"```[a-zA-Z]*\n(.*?)\n```", after_heading, flags=re.DOTALL)
    assert blocks, "Worked example fenced code block not found"
    return blocks


def _section(text: str, start_heading: str, end_heading: str | None) -> str:
    """Return the spec text from start_heading up to end_heading (exclusive).

    Scopes a token assertion to the section that is supposed to contain it, so a
    test cannot pass on a token that merely survives in some other section. Both
    headings must be present and ordered; end_heading=None runs to end of file.
    """
    start = text.index(start_heading)
    if end_heading is None:
        return text[start:]
    end = text.index(end_heading, start + len(start_heading))
    return text[start:end]


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

    Scoped to §5 so the assertion cannot pass on tokens that merely survive in
    the Java guardrails or the pre-existing degeneration-trigger section.
    """
    section = _section(
        SPEC_PATH.read_text(encoding="utf-8"),
        "### 5. plans/stepNN.md",
        "## Worked example:",
    )
    for token in ("slice", "@RestClientTest", "@SpringBootTest", "full application context"):
        assert token in section, f"§5 wiring rule missing slice-vs-context-load token: {token}"


def test_java_http_client_consistency_guardrail_present() -> None:
    """The Java guardrails must cover HTTP-client / dependency consistency.

    The canonical local-model failure mixes a reactive client with the servlet
    starter (WebClient configured via RestClient-only requestFactory(...), or a
    WebClient service tested with @RestClientTest). The spec must name this so a
    planner ties the client to the declared starter.

    Scoped to the Java guardrails section; tokens are uniquely meaningful there
    (no substring-of-another-token freebies like starter-web ⊂ starter-webflux).
    """
    section = _section(SPEC_PATH.read_text(encoding="utf-8"), "### Java", None)
    for token in ("HTTP-client", "WebClient", "requestFactory",
                  "ClientHttpConnector", "spring-webflux"):
        assert token in section, f"Java HTTP-client guardrail missing token: {token}"


def test_java_package_to_directory_guardrail_present() -> None:
    """The Java guardrails must teach package-name → directory-path mapping.

    A local executor improvises the source layout when a step leaves it
    implicit, producing the package name as a single dotted directory
    (src/main/java/com.example/...) or a parenthesised root
    (src/main/java(com.example.app)/...). The spec must state the dot→slash
    mapping and require steps to list full slash-separated paths. Regressing
    this reopens the layout bug that got steps rejected during Phase 2.

    Scoped to the Java guardrails section.
    """
    section = _section(SPEC_PATH.read_text(encoding="utf-8"), "### Java", None)
    for token in ("Package-to-directory mapping", "com.example.app0501",
                  "com/example/app0501", "Files to change"):
        assert token in section, f"Java package→directory guardrail missing token: {token}"


def test_context_md_section_requires_naming_and_paths() -> None:
    """§0 must require CONTEXT.md to pin naming & path conventions.

    CONTEXT.md is read on every step, so it is the place to fix the exact base
    package, its directory path, and the precise module name with its digit
    count (app0501, four digits) — the concrete values the executor got wrong.

    Scoped to §0 so the tokens prove the rule lives in the CONTEXT.md section.
    """
    section = _section(
        SPEC_PATH.read_text(encoding="utf-8"),
        "### 0. CONTEXT.md",
        "### 1. PLAN.md",
    )
    for token in ("Naming & path conventions", "digit count", "app0501"):
        assert token in section, f"§0 CONTEXT.md section missing naming/paths token: {token}"


def test_verify_sh_requires_exit_propagation_and_static_guards() -> None:
    """§4 must require exit-status propagation and allow cheap static defect guards.

    The lesson from the field failure: a gate that swallows a non-zero build
    status reports "tests passed" on code that does not compile. The spec must
    require propagating the real status and permit a fast grep-based backstop.

    Scoped to §4 so the tokens prove the rule lives in the verify.sh section.
    """
    section = _section(
        SPEC_PATH.read_text(encoding="utf-8"),
        "### 4. verify.sh",
        "### 5. plans/stepNN.md",
    )
    for token in ("PIPESTATUS", "exit status", "Static defect guards"):
        assert token in section, f"§4 verify.sh section missing gate-hardening token: {token}"


def test_verify_sh_missing_toolchain_must_fail() -> None:
    """§4 must scope the uninitialized exit-0 allowance to the sentinel only.

    The 0609 Python runs shipped a verify.sh that exited 0 when .venv was
    missing, so phase2.sh recorded a step DONE without running any tests. The
    spec must say: missing sentinel → exit 0; missing toolchain/environment on
    an initialized project → non-zero infrastructure failure.
    """
    section = _section(
        SPEC_PATH.read_text(encoding="utf-8"),
        "### 4. verify.sh",
        "### 5. plans/stepNN.md",
    )
    for token in ("Missing-toolchain rule", ".venv", "infrastructure failure", "non-zero"):
        assert token in section, f"§4 verify.sh section missing toolchain-rule token: {token}"


def test_verify_sh_requires_direct_exit_capture() -> None:
    """§4 must forbid reading `$?` inside the body of `if ! cmd`.

    The 0609 Java run committed a broken pom.xml as a passing step because the
    generated verify.sh used `if ! wait "$pid"; then status=$?` — inside that
    branch $? is the status of the negated test (always 0). The spec must name
    the anti-pattern and the correct capture.
    """
    section = _section(
        SPEC_PATH.read_text(encoding="utf-8"),
        "### 4. verify.sh",
        "### 5. plans/stepNN.md",
    )
    for token in ("Capture exit status immediately", "negated", "cmd || rc=$?"):
        assert token in section, f"§4 verify.sh section missing exit-capture token: {token}"


def test_java_build_file_edit_guardrail_present() -> None:
    """The Java guardrails must cover build-file coordinate fidelity.

    The 0609 step01 regenerated the whole scaffold pom.xml and corrupted
    spring-boot-starter-parent into spring-boot-starters-parent (plus
    starter→started drift). The spec must require minimal anchored build-file
    edits and name the corruption class phase2.sh backstops.
    """
    section = _section(SPEC_PATH.read_text(encoding="utf-8"), "### Java", None)
    for token in ("Build-file edits", "spring-boot-starters-parent",
                  "never instruct a full-file rewrite"):
        assert token in section, f"Java build-file guardrail missing token: {token}"

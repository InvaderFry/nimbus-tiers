"""CLI entry for `setupEnvironment.py` / `nimbus-setup`."""

from __future__ import annotations

import argparse
import sys
from typing import Mapping, Sequence

from nimbus_tiers.environment.environment_setup import EnvironmentSetup
from nimbus_tiers.environment.setup_step import SetupStep
from nimbus_tiers.environment.steps import (
    AiderStep,
    ClaudeCodeStep,
    GroqApiKeyStep,
    NvidiaDriverStep,
    OllamaServerConfigStep,
    OllamaStep,
    PythonStep,
    TabbyApiStep,
)


def _full_hybrid_steps() -> list[SetupStep]:
    """Path C step ordering — host prerequisites first, runtimes second."""
    return [
        PythonStep(),
        NvidiaDriverStep(),
        OllamaStep(),
        OllamaServerConfigStep(),
        TabbyApiStep(),
        AiderStep(),
        GroqApiKeyStep(),
        ClaudeCodeStep(),
    ]


def _light_local_steps() -> list[SetupStep]:
    """Path B: Ollama only — no TabbyAPI/ExLlamaV3.

    The NVIDIA driver stays in the list as an advisory check: Ollama runs on
    CPU, but a GPU is what makes a 14B executor usable. The Groq key stays
    because phase2.sh's PHASE2_FALLBACK_MODEL escalation defaults to Groq.
    """
    return [
        PythonStep(),
        NvidiaDriverStep(),
        OllamaStep(),
        OllamaServerConfigStep(),
        AiderStep(),
        GroqApiKeyStep(),
        ClaudeCodeStep(),
    ]


def _cloud_only_steps() -> list[SetupStep]:
    """Path A: no local models — just the tools and the Groq credential."""
    return [
        PythonStep(),
        AiderStep(),
        GroqApiKeyStep(),
        ClaudeCodeStep(),
    ]


PATH_REGISTRY: Mapping[str, "callable[[], list[SetupStep]]"] = {
    "full-hybrid": _full_hybrid_steps,
    "light-local": _light_local_steps,
    "cloud-only": _cloud_only_steps,
}


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="setupEnvironment",
        description=(
            "Check (and optionally install) the runtime stack required by the "
            "Hybrid AI Coding Architecture. Idempotent: nothing is modified "
            "without an interactive prompt unless --yes is set."
        ),
    )
    parser.add_argument(
        "--path-type",
        choices=sorted(PATH_REGISTRY.keys()),
        default="full-hybrid",
        help=(
            "Which setup path's stack to check: full-hybrid (Ollama + TabbyAPI "
            "+ cloud), light-local (Ollama only), or cloud-only (no local models)."
        ),
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only run check(); do not prompt for or perform installs. "
        "Exits 0 if everything is present, 1 otherwise.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Accept all install prompts non-interactively. Use with caution.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    steps = PATH_REGISTRY[args.path_type]()
    setup = EnvironmentSetup(steps)

    print(f"Running environment setup ({args.path_type})")
    if args.check_only:
        print("Mode: check only — no installs will be attempted.")
    elif args.yes:
        print("Mode: --yes — installs will proceed without prompting.")
    print()

    report = setup.run(check_only=args.check_only, assume_yes=args.yes)

    print(report.render())
    print()

    if report.all_present:
        print("Environment ready.")
        return 0

    print("One or more steps are still missing. See output above for next actions.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

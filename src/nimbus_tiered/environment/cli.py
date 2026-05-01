"""CLI entry for `setupEnvironment.py` / `nimbus-setup`."""

from __future__ import annotations

import argparse
import sys
from typing import Mapping, Sequence

from nimbus_tiered.environment.environment_setup import EnvironmentSetup
from nimbus_tiered.environment.setup_step import EnvVarStep, SetupStep
from nimbus_tiered.environment.steps import (
    AiderStep,
    ClaudeCodeStep,
    GroqApiKeyStep,
    NvidiaDriverStep,
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
        EnvVarStep("OLLAMA_FLASH_ATTENTION", "1"),
        EnvVarStep("OLLAMA_KV_CACHE_TYPE", "q8_0"),
        TabbyApiStep(),
        AiderStep(),
        GroqApiKeyStep(),
        ClaudeCodeStep(),
    ]


PATH_REGISTRY: Mapping[str, "callable[[], list[SetupStep]]"] = {
    "full-hybrid": _full_hybrid_steps,
    "cloud-only": lambda: _not_implemented("cloud-only"),
    "light-local": lambda: _not_implemented("light-local"),
}


def _not_implemented(path_type: str) -> list[SetupStep]:
    raise SystemExit(
        f"setupEnvironment for --path-type {path_type} is not yet implemented. "
        "Use --path-type full-hybrid for now."
    )


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
        help="Which setup path's stack to check. Currently only 'full-hybrid' is implemented.",
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

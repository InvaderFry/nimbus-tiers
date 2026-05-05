"""CLI entry point for `generateNewProject.py` / `nimbus-generate`."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Mapping

from nimbus_tiers.generator.cloud_only_path import CloudOnlyPath
from nimbus_tiers.generator.file_writer import FileWriter, WriteMode
from nimbus_tiers.generator.full_hybrid_path import FullHybridPath
from nimbus_tiers.generator.git_initializer import GitInitializer
from nimbus_tiers.generator.light_local_path import LightLocalPath
from nimbus_tiers.generator.project_generator import ProjectGenerator
from nimbus_tiers.generator.setup_path import SetupPath


PROJECT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

PATH_REGISTRY: Mapping[str, type[SetupPath]] = {
    "full-hybrid": FullHybridPath,
    "cloud-only": CloudOnlyPath,
    "light-local": LightLocalPath,
}

STACK_TEST_COMMANDS: Mapping[str, str] = {
    "python": "pytest -x --no-header",
    "java-maven": "./mvnw test",
    "java-gradle": "./gradlew test",
    "node": "npm test",
}


def _repo_root() -> Path:
    """Return the nimbus-tiers repo root (two levels up from this file)."""
    return Path(__file__).resolve().parents[3]


def _default_project_path(project_name: str) -> Path:
    """Default destination = sibling directory of the template repo."""
    return _repo_root().parent / project_name


def _select_mode(args: argparse.Namespace) -> WriteMode:
    if args.diff:
        return WriteMode.DIFF
    if args.force:
        return WriteMode.FORCE
    return WriteMode.SKIP


def _derive_package_name(project_name: str) -> str:
    """my-app -> myapp  (lowercase alphanumeric; prefix 'app' if starts with digit)."""
    pkg = re.sub(r"[^a-z0-9]", "", project_name.lower()) or "app"
    return ("app" + pkg) if pkg[0].isdigit() else pkg


def _derive_class_name(project_name: str) -> str:
    """my-app -> MyApp  (PascalCase from dash/underscore-separated words)."""
    parts = re.split(r"[-_]+", project_name)
    cls = "".join(p.capitalize() for p in parts if p)
    return ("App" + cls) if (cls and cls[0].isdigit()) else (cls or "App")


def _validate_project_name(name: str) -> str:
    if not PROJECT_NAME_RE.match(name):
        raise SystemExit(
            f"Invalid project name {name!r}. Must match {PROJECT_NAME_RE.pattern}"
        )
    return name


def _prompt_project_name() -> str:
    try:
        name = input("Project name: ").strip()
    except EOFError:
        raise SystemExit("project_name is required (no TTY for interactive prompt)")
    if not name:
        raise SystemExit("project_name cannot be empty")
    return _validate_project_name(name)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generateNewProject",
        description=(
            "Scaffold a new project pre-wired for the Hybrid AI Coding Architecture. "
            "Default destination is one directory above this template repo."
        ),
    )
    parser.add_argument(
        "project_name",
        nargs="?",
        help="Name of the new project (alphanumeric, dash, underscore). "
        "If omitted, you will be prompted.",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Destination directory. Defaults to ../<project_name> next to this repo.",
    )
    parser.add_argument(
        "--path-type",
        choices=sorted(PATH_REGISTRY.keys()),
        default="full-hybrid",
        help="Setup path. Currently only 'full-hybrid' is implemented.",
    )
    parser.add_argument(
        "--stack",
        choices=sorted(STACK_TEST_COMMANDS.keys()),
        default="java-maven",
        help=(
            "Project technology stack. Sets the Aider auto-test command in "
            ".aider.conf.yml. Choices: "
            + ", ".join(f"{k} ({v!r})" for k, v in sorted(STACK_TEST_COMMANDS.items()))
            + ". Defaults to 'java-maven'."
        ),
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files in the destination.",
    )
    mode_group.add_argument(
        "--diff",
        action="store_true",
        help="Print a unified diff of what would change. Write nothing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    project_name = (
        _validate_project_name(args.project_name)
        if args.project_name
        else _prompt_project_name()
    )

    project_path = (
        args.path.resolve() if args.path is not None else _default_project_path(project_name)
    )

    repo_root = _repo_root()
    if project_path == repo_root or repo_root in project_path.parents:
        raise SystemExit(
            f"Refusing to generate into the template repo itself ({project_path})."
        )

    package_name = _derive_package_name(project_name)
    class_name = _derive_class_name(project_name)
    test_cmd = STACK_TEST_COMMANDS[args.stack]

    if args.path_type == "full-hybrid":
        setup_path = FullHybridPath(
            stack=args.stack,
            package_name=package_name,
            class_name=class_name,
        )
    else:
        setup_path = PATH_REGISTRY[args.path_type]()

    file_writer = FileWriter(mode=_select_mode(args))
    git_initializer = GitInitializer()
    templates_root = repo_root / "templates"

    generator = ProjectGenerator(
        setup_path=setup_path,
        file_writer=file_writer,
        git_initializer=git_initializer,
        templates_root=templates_root,
    )

    print(f"Generating {args.path_type} project '{project_name}' at {project_path}")
    print(f"Templates root: {templates_root}")
    print(f"Stack: {args.stack} (test-cmd: {test_cmd!r})")
    print()

    try:
        report = generator.generate(
            project_name,
            project_path,
            substitutions={
                "TEST_CMD": test_cmd,
                "PACKAGE_NAME": package_name,
                "CLASS_NAME": class_name,
            },
        )
    except NotImplementedError as exc:
        raise SystemExit(str(exc))

    print()
    print(report.render())

    if args.diff:
        print()
        print("Diff mode: no files were written.")
    else:
        print()
        print("Next steps:")
        print(f"  cd {project_path}")
        print("  claude            # Phase 1: write PLAN.md and TESTS.md, refine CONTEXT.md")
        print("  aider --read PLAN.md --read TESTS.md --read CONTEXT.md   # Phase 2")
        print("  claude            # Phase 3: review the diff against PLAN.md")

    return 0


if __name__ == "__main__":
    sys.exit(main())

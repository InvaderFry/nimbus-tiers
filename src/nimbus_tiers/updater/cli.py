"""CLI entry point for `updateProject.py` / `nimbus-update`.

phase2.sh and the other tool-owned scaffold files keep receiving fixes in the
nimbus-tiers templates, but a generated project holds a frozen copy from
generation day. This tool re-syncs the *managed* subset (TemplateSpec.managed)
of an existing project against the current templates:

- `--diff` (default) previews what would change, writing nothing.
- `--apply` overwrites managed files whose content differs.
- `--force-all` extends the update to user-owned files too (CONTEXT.md,
  .aider.conf.yml, stack starters, ...) — destructive to local edits.

Which path/stack the project was generated with is read from the
`.nimbus-tiers.json` manifest the generator writes; projects generated before
the manifest existed can supply `--path-type`/`--stack` explicitly.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Sequence

from nimbus_tiers.generator.cli import (
    PATH_REGISTRY,
    STACK_TEST_COMMANDS,
    derive_class_name,
    derive_package_name,
)
from nimbus_tiers.generator.file_writer import FileWriter, WriteMode, WriteResult
from nimbus_tiers.generator.project_generator import (
    MANIFEST_NAME,
    render_manifest,
)
from nimbus_tiers.resources import templates_root


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nimbus-update",
        description=(
            "Re-sync the tool-owned scaffold files (phase2.sh, phase2-lib.sh, "
            "PHASE1_SPEC.md, ...) of a generated project against the current "
            "nimbus-tiers templates. User-owned files (CONTEXT.md, "
            ".aider.conf.yml, your source code) are never touched unless "
            "--force-all is given."
        ),
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Project directory to update. Defaults to the current directory.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--diff",
        action="store_true",
        help="Preview: print a unified diff of what would change. Default mode.",
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help="Overwrite managed files whose content differs from the template.",
    )
    mode_group.add_argument(
        "--force-all",
        action="store_true",
        help=(
            "Like --apply, but also overwrite user-owned files (CONTEXT.md, "
            ".aider.conf.yml, stack starters, ...). Destroys local edits to "
            "those files — make sure everything is committed first."
        ),
    )
    parser.add_argument(
        "--path-type",
        choices=sorted(PATH_REGISTRY.keys()),
        default=None,
        help="Override (or supply, for pre-manifest projects) the setup path.",
    )
    parser.add_argument(
        "--stack",
        choices=sorted(STACK_TEST_COMMANDS.keys()),
        default=None,
        help="Override (or supply, for pre-manifest projects) the tech stack.",
    )
    return parser


def _read_manifest(project_path: Path) -> dict:
    manifest_path = project_path / MANIFEST_NAME
    if not manifest_path.is_file():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Could not parse {manifest_path}: {exc}")
    if not isinstance(data, dict):
        raise SystemExit(f"{manifest_path} is not a JSON object.")
    return data


def _git_dirty_paths(project_path: Path) -> list[str] | None:
    """Return dirty paths, [] if clean, or None when not a usable git repo."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    return [line for line in proc.stdout.splitlines() if line.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    project_path = args.path.resolve()
    if not project_path.is_dir():
        raise SystemExit(f"Project directory not found: {project_path}")

    manifest = _read_manifest(project_path)
    path_type = args.path_type or manifest.get("path_type")
    stack = args.stack or manifest.get("stack")
    if not path_type or not stack:
        raise SystemExit(
            f"No usable {MANIFEST_NAME} in {project_path} and no --path-type/--stack "
            "given. Projects generated before the manifest existed must pass both "
            "flags explicitly (e.g. --path-type full-hybrid --stack python)."
        )
    if path_type not in PATH_REGISTRY:
        raise SystemExit(f"Unknown path_type {path_type!r} (from manifest or flags).")
    if stack not in STACK_TEST_COMMANDS:
        raise SystemExit(f"Unknown stack {stack!r} (from manifest or flags).")

    project_name = manifest.get("project_name") or project_path.name
    package_name = manifest.get("package_name") or derive_package_name(project_name)
    class_name = manifest.get("class_name") or derive_class_name(project_name)

    apply_mode = args.apply or args.force_all
    if apply_mode:
        dirty = _git_dirty_paths(project_path)
        if dirty:
            raise SystemExit(
                "Refusing to update: the project working tree has uncommitted "
                "changes. Commit or stash them first so the update lands as a "
                "single reviewable diff.\n  " + "\n  ".join(dirty)
            )

    setup_path = PATH_REGISTRY[path_type](
        stack=stack,
        package_name=package_name,
        class_name=class_name,
    )
    specs = [
        spec
        for spec in setup_path.template_files()
        if spec.managed or args.force_all
    ]

    substitutions = {
        "PROJECT_NAME": project_name,
        "TEST_CMD": STACK_TEST_COMMANDS[stack],
        "PACKAGE_NAME": package_name,
        "CLASS_NAME": class_name,
    }

    writer = FileWriter(mode=WriteMode.FORCE if apply_mode else WriteMode.DIFF)
    templates_dir = templates_root()

    scope = "managed + user-owned" if args.force_all else "managed"
    print(f"Updating {scope} scaffold files for '{project_name}' at {project_path}")
    print(f"Path type: {path_type}, stack: {stack}")
    print(f"Templates: {templates_dir}")
    print()

    results: list[WriteResult] = []
    for spec in specs:
        results.append(
            writer.write(
                templates_dir / spec.src_relative,
                project_path / spec.dest_relative,
                substitutions,
            )
        )
    # Keep the manifest itself current (writes one for pre-manifest projects).
    results.append(
        writer.write_content(
            render_manifest(project_name, setup_path, substitutions),
            project_path / MANIFEST_NAME,
        )
    )

    counts = Counter(r.action.value for r in results)
    for action, count in sorted(counts.items()):
        print(f"  {action:>10s}: {count}")
    changed = [r for r in results if r.action.value == "written"]
    if apply_mode and changed:
        print()
        print("Updated files:")
        for r in changed:
            print(f"  {r.dest}")
        print()
        print("Review with `git diff`, then commit the update as its own commit.")
    elif not apply_mode:
        print()
        print("Diff mode: nothing was written. Re-run with --apply to update.")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())

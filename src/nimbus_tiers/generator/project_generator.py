"""Orchestrator that scaffolds a new project from a SetupPath.

Composes a SetupPath, a FileWriter, and a GitInitializer via constructor injection
so each piece can be swapped or mocked in tests. The orchestrator itself is small
and path-agnostic — adding a new SetupPath subclass requires no changes here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from nimbus_tiers.generator.file_writer import FileWriter, WriteAction, WriteResult
from nimbus_tiers.generator.git_initializer import (
    GitInitAction,
    GitInitializer,
    GitInitResult,
)
from nimbus_tiers.generator.setup_path import SetupPath


@dataclass
class GenerationReport:
    project_name: str
    project_path: Path
    setup_path_name: str
    file_results: list[WriteResult] = field(default_factory=list)
    git_result: GitInitResult | None = None

    def summary(self) -> dict[str, int]:
        counts: Counter[str] = Counter(r.action.value for r in self.file_results)
        return dict(counts)

    def render(self) -> str:
        lines = [
            f"Project:    {self.project_name}",
            f"Path:       {self.project_path}",
            f"Setup type: {self.setup_path_name}",
            "",
            "Files:",
        ]
        for action, count in sorted(self.summary().items()):
            lines.append(f"  {action:>10s}: {count}")
        if self.git_result is not None:
            lines.append("")
            lines.append(f"Git:        {self.git_result.action.value} ({self.git_result.detail})")
        return "\n".join(lines)


class ProjectGenerator:
    """Composes a SetupPath + FileWriter + GitInitializer to scaffold a project."""

    def __init__(
        self,
        setup_path: SetupPath,
        file_writer: FileWriter,
        git_initializer: GitInitializer,
        templates_root: Path,
    ) -> None:
        self.setup_path = setup_path
        self.file_writer = file_writer
        self.git_initializer = git_initializer
        self.templates_root = templates_root

    def generate(
        self,
        project_name: str,
        project_path: Path,
        substitutions: Mapping[str, str] | None = None,
    ) -> GenerationReport:
        if project_path.exists() and project_path.is_file():
            raise NotADirectoryError(
                f"Destination exists and is a file, expected directory: {project_path}"
            )

        self.setup_path.validate()
        project_path.mkdir(parents=True, exist_ok=True)

        merged_subs: dict[str, str] = {"PROJECT_NAME": project_name}
        if substitutions:
            merged_subs.update(substitutions)

        report = GenerationReport(
            project_name=project_name,
            project_path=project_path,
            setup_path_name=self.setup_path.name,
        )

        for spec in self.setup_path.template_files():
            src = self.templates_root / spec.src_relative
            dest = project_path / spec.dest_relative
            report.file_results.append(self.file_writer.write(src, dest, merged_subs))

        self.setup_path.post_copy_hooks(project_path)
        report.git_result = self.git_initializer.initialize(project_path)
        return report


__all__ = ["ProjectGenerator", "GenerationReport"]

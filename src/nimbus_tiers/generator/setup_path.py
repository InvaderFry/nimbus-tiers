"""Abstract base class for setup paths.

A SetupPath captures *which template files get copied into a new project* and
*what post-copy hooks need to run*. Concrete subclasses (FullHybridPath,
CloudOnlyPath, LightLocalPath) differ only in the file list and hooks they
declare — the orchestrator is path-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TemplateSpec:
    """One template-file mapping: where to read from, where to write to.

    Both paths are relative — `src_relative` to the templates root, `dest_relative`
    to the new-project root. Absolute paths are forbidden so paths stay portable
    across machines and so the orchestrator can swap roots freely.
    """

    src_relative: Path
    dest_relative: Path

    def __post_init__(self) -> None:
        if self.src_relative.is_absolute():
            raise ValueError(
                f"src_relative must be relative, got absolute: {self.src_relative}"
            )
        if self.dest_relative.is_absolute():
            raise ValueError(
                f"dest_relative must be relative, got absolute: {self.dest_relative}"
            )


class SetupPath(ABC):
    """Abstract base class. Subclass per setup path (Cloud-Only, Light Local, Full Hybrid)."""

    name: str = "abstract"

    @abstractmethod
    def template_files(self) -> list[TemplateSpec]:
        """Return the list of template files this path scaffolds.

        Each TemplateSpec maps a file under the templates root to a destination
        path under the new project root.
        """
        raise NotImplementedError

    def post_copy_hooks(self, project_root: Path) -> None:
        """Run after all template files are copied. Default: no-op.

        Subclasses can override to perform path-specific setup (e.g., write a
        path-flavored config based on detected hardware).
        """
        del project_root  # unused by default

    def validate(self) -> None:
        """Sanity-check the spec list. Called by orchestrator before copying."""
        specs = self.template_files()
        seen_dests: set[Path] = set()
        for spec in specs:
            if spec.dest_relative in seen_dests:
                raise ValueError(
                    f"Duplicate destination in {type(self).__name__}: {spec.dest_relative}"
                )
            seen_dests.add(spec.dest_relative)


__all__ = ["SetupPath", "TemplateSpec"]

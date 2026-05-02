"""Path A: Cloud-Only setup. Stub — not yet implemented."""

from __future__ import annotations

from nimbus_tiers.generator.setup_path import SetupPath, TemplateSpec


class CloudOnlyPath(SetupPath):
    name = "cloud-only"

    def template_files(self) -> list[TemplateSpec]:
        raise NotImplementedError(
            "CloudOnlyPath (Path A) is planned but not yet implemented. "
            "Track in BuildThisRepoFromArchitecture.md follow-ups. "
            "Use --path-type full-hybrid for now."
        )


__all__ = ["CloudOnlyPath"]

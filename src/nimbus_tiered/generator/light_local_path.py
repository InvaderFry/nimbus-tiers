"""Path B: Light Local setup (Ollama only, no TabbyAPI). Stub — not yet implemented."""

from __future__ import annotations

from nimbus_tiered.generator.setup_path import SetupPath, TemplateSpec


class LightLocalPath(SetupPath):
    name = "light-local"

    def template_files(self) -> list[TemplateSpec]:
        raise NotImplementedError(
            "LightLocalPath (Path B) is planned but not yet implemented. "
            "Track in BuildThisRepoFromArchitecture.md follow-ups. "
            "Use --path-type full-hybrid for now."
        )


__all__ = ["LightLocalPath"]

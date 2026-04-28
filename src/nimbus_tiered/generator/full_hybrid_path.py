"""Path C: Full Hybrid setup (Ollama + TabbyAPI/ExLlamaV3 + cloud subscriptions).

This is the only fully-implemented setup path in the current iteration. The file
list mirrors the architecture doc's "What gets copied into the new project"
section.
"""

from __future__ import annotations

from pathlib import Path

from nimbus_tiered.generator.setup_path import SetupPath, TemplateSpec


class FullHybridPath(SetupPath):
    name = "full-hybrid"

    def template_files(self) -> list[TemplateSpec]:
        # Each tuple is (src under templates/, dest under project root).
        # Hidden dotfiles preserve their leading dot at the destination.
        mapping: list[tuple[str, str]] = [
            ("CONTEXT.md", "CONTEXT.md"),
            ("VERIFY.md", "VERIFY.md"),
            ("CLAUDE.md", "CLAUDE.md"),
            ("README.md", "README.md"),
            (".aider.conf.yml", ".aider.conf.yml"),
            (".aiderignore", ".aiderignore"),
            (".gitignore", ".gitignore"),
            ("plans/README.md", "plans/README.md"),
            ("logs/ai-routing.csv", "logs/ai-routing.csv"),
            ("docs/architecture.md", "docs/architecture.md"),
        ]
        return [TemplateSpec(Path(src), Path(dest)) for src, dest in mapping]


__all__ = ["FullHybridPath"]

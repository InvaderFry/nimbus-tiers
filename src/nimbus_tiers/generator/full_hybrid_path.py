"""Path C: Full Hybrid setup (Ollama + TabbyAPI/ExLlamaV3 + cloud subscriptions).

The scaffold is shared with the other paths (StackScaffoldPath); this path
adds the TabbyAPI-flavored Aider config (via `paths/full-hybrid/`) and the
ready-to-copy TabbyAPI server example.
"""

from __future__ import annotations

from pathlib import Path

from nimbus_tiers.generator.setup_path import TemplateSpec
from nimbus_tiers.generator.stack_scaffold_path import StackScaffoldPath


class FullHybridPath(StackScaffoldPath):
    name = "full-hybrid"

    def extra_docs(self) -> list[TemplateSpec]:
        return [
            TemplateSpec(
                Path("tabbyapi-nimbus-example.yml"),
                Path("docs/tabbyapi-nimbus-example.yml"),
                managed=True,
            )
        ]


__all__ = ["FullHybridPath"]

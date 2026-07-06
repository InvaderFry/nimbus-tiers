"""Path B: Light Local setup (Ollama only — no TabbyAPI, no ExLlamaV3).

Same scaffold as the other paths; the Aider config (`paths/light-local/`)
points at Ollama's OpenAI-compatible endpoint on localhost:11434 instead of
TabbyAPI, so no TabbyAPI example doc is copied.
"""

from __future__ import annotations

from nimbus_tiers.generator.stack_scaffold_path import StackScaffoldPath


class LightLocalPath(StackScaffoldPath):
    name = "light-local"


__all__ = ["LightLocalPath"]

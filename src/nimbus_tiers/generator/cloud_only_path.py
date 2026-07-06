"""Path A: Cloud-Only setup (Groq + frontier subscriptions — no local models).

Same scaffold as the other paths; the Aider config (`paths/cloud-only/`)
targets Groq's hosted models via GROQ_API_KEY, so there is no local endpoint
or TabbyAPI example doc.
"""

from __future__ import annotations

from nimbus_tiers.generator.stack_scaffold_path import StackScaffoldPath


class CloudOnlyPath(StackScaffoldPath):
    name = "cloud-only"


__all__ = ["CloudOnlyPath"]

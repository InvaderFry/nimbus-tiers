#!/usr/bin/env python3
"""Thin CLI shim. Delegates to nimbus_tiered.generator.cli:main."""

from __future__ import annotations

import sys
from pathlib import Path

# Make the in-repo `src/` package importable when running directly without
# `pip install -e .`.
_HERE = Path(__file__).resolve().parent
_SRC = _HERE / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from nimbus_tiered.generator.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

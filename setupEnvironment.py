#!/usr/bin/env python3
"""Thin CLI shim. Delegates to nimbus_tiers.environment.cli:main."""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = _HERE / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from nimbus_tiers.environment.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

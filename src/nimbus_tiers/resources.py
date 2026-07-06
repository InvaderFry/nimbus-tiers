"""Locate packaged resources so both install modes resolve the same way.

The templates tree lives inside the package (``nimbus_tiers/templates``) so it
ships in wheels. ``importlib.resources`` resolves it identically for a source
checkout (``src/`` layout), an editable install, and a site-packages install.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def templates_root() -> Path:
    """Return the on-disk path of the packaged templates tree.

    Raises FileNotFoundError if the templates did not ship with the package
    (e.g. a wheel built without package data) — a clear error here beats a
    FileNotFoundError on the first template copy.
    """
    root = Path(str(files("nimbus_tiers").joinpath("templates")))
    if not root.is_dir():
        raise FileNotFoundError(
            f"Packaged templates not found at {root}. The nimbus-tiers install is "
            "missing its package data; reinstall from source or a complete wheel."
        )
    return root


def source_checkout_root() -> Path | None:
    """Return the repo root when running from a source checkout, else None.

    Detected by the ``pyproject.toml`` + ``.git`` pair two levels above the
    package (the ``src/`` layout). A site-packages or pipx install has neither,
    so callers can branch on checkout-specific behavior (default destination,
    self-generation guard).
    """
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "pyproject.toml").is_file() and (candidate / ".git").exists():
        return candidate
    return None


__all__ = ["templates_root", "source_checkout_root"]

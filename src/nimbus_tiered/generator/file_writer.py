"""Idempotent file writer with skip / force / diff modes.

Centralizes the "check before override" policy that all template-copy operations
must follow. Three modes:

- SKIP   (default) — if the destination exists, leave it alone and log a warning.
- FORCE  — overwrite the destination unconditionally.
- DIFF   — print a unified diff between source (post-substitution) and destination,
           write nothing.
"""

from __future__ import annotations

import difflib
import enum
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping


class WriteMode(enum.Enum):
    SKIP = "skip"
    FORCE = "force"
    DIFF = "diff"


class WriteAction(enum.Enum):
    WRITTEN = "written"
    SKIPPED = "skipped"
    DIFFED = "diffed"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class WriteResult:
    action: WriteAction
    dest: Path
    detail: str = ""


class FileWriter:
    """Copies files with optional `{{KEY}}` substitution and idempotency checks.

    Substitution is applied only to text files (UTF-8 decodable). Binary files
    are copied byte-for-byte, ignoring the substitution dict.
    """

    def __init__(
        self,
        mode: WriteMode = WriteMode.SKIP,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.mode = mode
        self._log = log if log is not None else (lambda msg: print(msg, file=sys.stderr))

    def write(
        self,
        src_path: Path,
        dest_path: Path,
        substitutions: Mapping[str, str] | None = None,
    ) -> WriteResult:
        if not src_path.is_file():
            raise FileNotFoundError(f"Template source not found: {src_path}")
        if dest_path.exists() and dest_path.is_dir():
            raise IsADirectoryError(
                f"Destination exists as a directory, expected file: {dest_path}"
            )

        rendered = self._render(src_path, substitutions or {})

        if self.mode is WriteMode.DIFF:
            return self._diff(rendered, dest_path)

        if dest_path.exists():
            existing = self._read_bytes(dest_path)
            if existing == rendered:
                return WriteResult(WriteAction.UNCHANGED, dest_path, "identical")
            if self.mode is WriteMode.SKIP:
                self._log(f"[skip] {dest_path} already exists (use --force to overwrite)")
                return WriteResult(WriteAction.SKIPPED, dest_path, "exists")

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as fh:
            fh.write(rendered)
        return WriteResult(WriteAction.WRITTEN, dest_path)

    def _diff(self, rendered: bytes, dest_path: Path) -> WriteResult:
        if not dest_path.exists():
            self._log(f"[diff] would create new file: {dest_path}")
            return WriteResult(WriteAction.DIFFED, dest_path, "new file")

        existing = self._read_bytes(dest_path)
        if existing == rendered:
            self._log(f"[diff] no changes: {dest_path}")
            return WriteResult(WriteAction.DIFFED, dest_path, "no changes")

        try:
            existing_text = existing.decode("utf-8").splitlines(keepends=True)
            rendered_text = rendered.decode("utf-8").splitlines(keepends=True)
        except UnicodeDecodeError:
            self._log(f"[diff] binary file differs: {dest_path}")
            return WriteResult(WriteAction.DIFFED, dest_path, "binary differs")

        diff = difflib.unified_diff(
            existing_text,
            rendered_text,
            fromfile=str(dest_path),
            tofile=f"{dest_path} (template)",
        )
        for line in diff:
            self._log(line.rstrip("\n"))
        return WriteResult(WriteAction.DIFFED, dest_path, "diff printed")

    @staticmethod
    def _read_bytes(path: Path) -> bytes:
        with open(path, "rb") as fh:
            return fh.read()

    @classmethod
    def _render(cls, src_path: Path, substitutions: Mapping[str, str]) -> bytes:
        raw = cls._read_bytes(src_path)
        if not substitutions:
            return raw
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw  # binary file — pass through unchanged
        for key, value in substitutions.items():
            text = text.replace("{{" + key + "}}", value)
        return text.encode("utf-8")

    def copy_tree(
        self,
        src_root: Path,
        dest_root: Path,
        substitutions: Mapping[str, str] | None = None,
    ) -> list[WriteResult]:
        """Recursively copy every file under src_root into dest_root.

        Convenience for callers that want to scaffold a whole tree without
        listing every file. Returns one WriteResult per file processed.
        """
        if not src_root.is_dir():
            raise NotADirectoryError(f"Template root is not a directory: {src_root}")

        results: list[WriteResult] = []
        for src_file in sorted(src_root.rglob("*")):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(src_root)
            results.append(self.write(src_file, dest_root / rel, substitutions))
        return results


__all__ = ["FileWriter", "WriteMode", "WriteAction", "WriteResult"]

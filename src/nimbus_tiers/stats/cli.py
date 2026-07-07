"""CLI entry point for `analyzeRouting.py` / `nimbus-stats`.

phase2.sh appends one row to `logs/ai-routing.csv` per recorded step (columns:
date,repo,task_type,tier_used,model,escalated_from,tests_passed,
diff_lines_approx,human_rework_minutes,outcome). This tool turns that log into
the routing summary the architecture doc promises — tier share, escalation
rate, per-model counts, diff sizes — so tier decisions can be made from data.

Known limitation, by design: FAILED runs are not in the CSV. phase2.sh logs a
row only on the `done` and `halted` paths, because a failure row would dirty
the working tree and wedge the next run's dirty-tree guard. Escalation rate
(fallback rows / total) is therefore the honest proxy for "the local tier
needed help", not a failure rate.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence

EXPECTED_COLUMNS = [
    "date",
    "repo",
    "task_type",
    "tier_used",
    "model",
    "escalated_from",
    "tests_passed",
    "diff_lines_approx",
    "human_rework_minutes",
    "outcome",
]


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nimbus-stats",
        description=(
            "Summarize a generated project's logs/ai-routing.csv: tier share, "
            "escalation rate, per-model counts, diff sizes. Note: failed runs "
            "are not logged (phase2.sh records only done/halted rows — a "
            "failure row would dirty the tree and block the next run), so "
            "escalation rate is the proxy for local-tier struggle."
        ),
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("logs/ai-routing.csv"),
        help="Path to the routing CSV. Defaults to logs/ai-routing.csv.",
    )
    return parser


def _fmt_pct(part: int, whole: int) -> str:
    return f"{100.0 * part / whole:.0f}%" if whole else "n/a"


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    log_path = args.log
    if not log_path.is_file():
        print(f"Routing log not found: {log_path}", file=sys.stderr)
        print(
            "Run this from a generated project root (or pass --log). The file is "
            "created by the first completed ./phase2.sh step.",
            file=sys.stderr,
        )
        return 1

    rows: list[dict[str, str]] = []
    malformed = 0
    with open(log_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or "outcome" not in reader.fieldnames:
            print(
                f"{log_path} has no parseable header (expected columns like "
                f"{','.join(EXPECTED_COLUMNS[:3])},...).",
                file=sys.stderr,
            )
            return 1
        for row in reader:
            # A row missing its outcome (short line, mid-write truncation)
            # cannot be classified — count it and move on.
            if not (row.get("outcome") or "").strip():
                malformed += 1
                continue
            rows.append(row)

    if not rows:
        print(f"{log_path} contains a header but no data rows yet.", file=sys.stderr)
        print("Rows are appended when ./phase2.sh records a step.", file=sys.stderr)
        return 1

    dates = sorted((row.get("date") or "").strip() for row in rows if (row.get("date") or "").strip())
    outcomes = Counter((row.get("outcome") or "").strip() for row in rows)
    tiers = Counter((row.get("tier_used") or "?").strip() for row in rows)
    models = Counter((row.get("model") or "?").strip() for row in rows)
    task_types = Counter((row.get("task_type") or "?").strip() for row in rows)
    escalated = sum(1 for row in rows if (row.get("escalated_from") or "").strip())

    diff_lines = []
    for row in rows:
        raw = (row.get("diff_lines_approx") or "").strip()
        if raw.isdigit():
            diff_lines.append(int(raw))

    total = len(rows)
    print(f"Routing summary — {log_path}")
    if dates:
        span = dates[0] if dates[0] == dates[-1] else f"{dates[0]} .. {dates[-1]}"
        print(f"  period:      {span}")
    print(f"  recorded:    {total} step run(s)"
          + (f" ({malformed} malformed row(s) skipped)" if malformed else ""))

    print("  outcomes:    " + ", ".join(
        f"{name}: {count}" for name, count in sorted(outcomes.items())
    ))
    print("  tier share:  " + ", ".join(
        f"tier {tier}: {count} ({_fmt_pct(count, total)})"
        for tier, count in sorted(tiers.items())
    ))
    print(f"  escalations: {escalated} of {total} ({_fmt_pct(escalated, total)}) "
          "ran on the fallback tier after a local failure")
    print("  models:      " + ", ".join(
        f"{model}: {count}" for model, count in models.most_common()
    ))
    if diff_lines:
        print(
            f"  diff lines:  total {sum(diff_lines)}, "
            f"mean {sum(diff_lines) / len(diff_lines):.0f}, "
            f"max {max(diff_lines)}"
        )
    if len(task_types) > 1:
        print("  task types:  " + ", ".join(
            f"{name}: {count}" for name, count in task_types.most_common()
        ))

    print()
    print("Note: failed runs are not logged (phase2.sh records done/halted only);")
    print("escalation rate is the proxy for how often the local tier needed help.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

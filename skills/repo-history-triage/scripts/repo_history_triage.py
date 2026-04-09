#!/usr/bin/env python3
"""Run lightweight repository-history diagnostics."""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from typing import Any

from triage_core import DEFAULT_BUG_PATTERN
from triage_core import LENS_ORDER
from triage_core import collect_report_data
from triage_core import repo_root


def print_pairs(title: str, rows: list[tuple[str, int]]) -> None:
    print(f"\n{title}")
    if not rows:
        print("  (none)")
        return
    for name, count in rows:
        print(f"  {count:>4}  {name}")


def print_lines(title: str, rows: list[str], limit: int | None = None) -> None:
    print(f"\n{title}")
    if not rows:
        print("  (none)")
        return
    for line in rows[:limit]:
        print(f"  {line}")


def print_text_report(report: dict[str, Any]) -> None:
    windows = report["windows"]
    tables = report["tables"]
    lens_summary = report["lens_summary"]

    print(report["title"])
    print(f"Repository: {report['repository']}")
    print(f"Window: {windows['since']}")
    print(f"Recent authors window: {windows['recent_authors_since']}")

    print("\nFive-Lens Overview")
    for key, label in LENS_ORDER:
        lens = lens_summary[key]
        print(
            f"  - {label} [{lens['status']}/{lens['severity']}/{lens['confidence']}]: {lens['summary']}"
        )

    print_pairs(
        "Churn Hotspots",
        [(row["path"], row["count"]) for row in tables["churn_hotspots"]],
    )
    print_pairs(
        "Overall Contributors",
        [(row["author"], row["count"]) for row in tables["overall_contributors"]],
    )
    print_pairs(
        "Recent Contributors",
        [(row["author"], row["count"]) for row in tables["recent_contributors"]],
    )
    print_pairs(
        "Bug Hotspots",
        [(row["path"], row["count"]) for row in tables["bug_hotspots"]],
    )
    print_pairs(
        "Commits By Month",
        [(row["month"], row["count"]) for row in tables["commits_by_month"]],
    )
    print_lines("Firefighting Commits", tables["firefighting_commits"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Path inside the target git repository.")
    parser.add_argument("--since", default="1 year ago", help='Window for churn, bugs, and firefighting. Default: "1 year ago".')
    parser.add_argument("--authors-since", default="6 months ago", help='Window for recent authorship. Default: "6 months ago".')
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format. Default: text.")
    parser.add_argument("--top", type=int, default=20, help="Number of rows to show for hotspot tables.")
    parser.add_argument("--bug-pattern", default=DEFAULT_BUG_PATTERN, help="Case-insensitive regex for bug-fix commit messages.")
    parser.add_argument("--fire-pattern", default=r"revert|hotfix|emergency|rollback", help="Case-insensitive regex for firefighting commits.")
    args = parser.parse_args()

    try:
        root = repo_root(pathlib.Path(args.repo).resolve())
        report = collect_report_data(
            root=root,
            since=args.since,
            authors_since=args.authors_since,
            top=args.top,
            bug_pattern=args.bug_pattern,
            fire_pattern=args.fire_pattern,
        )
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr or str(exc))
        return exc.returncode or 1

    if args.format == "json":
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print_text_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

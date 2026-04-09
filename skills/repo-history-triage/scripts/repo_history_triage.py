#!/usr/bin/env python3
"""Run lightweight repository-history diagnostics."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import subprocess
import sys
from typing import Iterable


SHORTLOG_RE = re.compile(r"^\s*(\d+)\s+(.+?)\s*$")


def run_git(repo: pathlib.Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def repo_root(repo: pathlib.Path) -> pathlib.Path:
    output = run_git(repo, ["rev-parse", "--show-toplevel"]).strip()
    return pathlib.Path(output)


def count_lines(lines: Iterable[str]) -> collections.Counter[str]:
    counter: collections.Counter[str] = collections.Counter()
    for line in lines:
        value = line.strip()
        if value:
            counter[value] += 1
    return counter


def parse_shortlog(raw: str) -> list[tuple[str, int]]:
    authors: list[tuple[str, int]] = []
    for line in raw.splitlines():
        match = SHORTLOG_RE.match(line)
        if not match:
            continue
        count, author = match.groups()
        authors.append((author, int(count)))
    return authors


def churn_hotspots(repo: pathlib.Path, since: str, top: int) -> list[tuple[str, int]]:
    raw = run_git(repo, ["log", "--format=format:", "--name-only", f"--since={since}"])
    return count_lines(raw.splitlines()).most_common(top)


def contributors(repo: pathlib.Path, since: str | None = None) -> list[tuple[str, int]]:
    args = ["shortlog", "-sn", "--no-merges"]
    if since:
        args.append(f"--since={since}")
    args.append("HEAD")
    return parse_shortlog(run_git(repo, args))


def bug_hotspots(repo: pathlib.Path, since: str, pattern: str, top: int) -> list[tuple[str, int]]:
    raw = run_git(
        repo,
        [
            "log",
            "-i",
            "-E",
            f"--grep={pattern}",
            "--name-only",
            "--format=",
            f"--since={since}",
        ],
    )
    return count_lines(raw.splitlines()).most_common(top)


def monthly_commits(repo: pathlib.Path) -> list[tuple[str, int]]:
    raw = run_git(repo, ["log", "--format=%ad", "--date=format:%Y-%m"])
    counts = count_lines(raw.splitlines())
    return sorted(counts.items())


def firefighting(repo: pathlib.Path, since: str, pattern: str) -> list[str]:
    raw = run_git(repo, ["log", "--oneline", f"--since={since}"])
    regex = re.compile(pattern, re.IGNORECASE)
    return [line for line in raw.splitlines() if regex.search(line)]


def recent_trend(monthly: list[tuple[str, int]]) -> str:
    if len(monthly) < 4:
        return "Insufficient monthly history for a trend call."

    recent = [count for _, count in monthly[-3:]]
    previous = [count for _, count in monthly[-9:-3]]
    if not previous:
        return "Insufficient prior history for a trend call."

    recent_avg = sum(recent) / len(recent)
    previous_avg = sum(previous) / len(previous)

    if previous_avg == 0:
        return "Insufficient prior history for a trend call."
    if recent_avg <= previous_avg * 0.6:
        return f"Recent commit volume is down ({recent_avg:.1f}/month vs {previous_avg:.1f}/month previously)."
    if recent_avg >= previous_avg * 1.4:
        return f"Recent commit volume is up ({recent_avg:.1f}/month vs {previous_avg:.1f}/month previously)."
    return f"Commit volume looks roughly steady ({recent_avg:.1f}/month vs {previous_avg:.1f}/month previously)."


def risk_notes(
    churn: list[tuple[str, int]],
    bugs: list[tuple[str, int]],
    overall_authors: list[tuple[str, int]],
    recent_authors: list[tuple[str, int]],
    monthly: list[tuple[str, int]],
    fire: list[str],
) -> list[str]:
    notes: list[str] = []

    bug_files = {path for path, _ in bugs}
    overlap = [path for path, _ in churn if path in bug_files]
    if overlap:
        notes.append("High-risk overlap: " + ", ".join(overlap[:5]))
    else:
        notes.append("High-risk overlap: none detected from commit-message keyword scan.")

    if overall_authors:
        total = sum(count for _, count in overall_authors)
        author, count = overall_authors[0]
        share = count / total if total else 0
        if share >= 0.6:
            notes.append(f"Ownership risk: {author} accounts for {share:.0%} of non-merge commits.")
        else:
            notes.append(f"Ownership risk: no single author dominates overall history ({author} leads at {share:.0%}).")

        recent_names = {name for name, _ in recent_authors}
        if author not in recent_names:
            notes.append(f"Continuity risk: top historical contributor {author} is absent from the recent window.")
    else:
        notes.append("Ownership risk: insufficient author history for a shortlog signal.")

    notes.append("Delivery trend: " + recent_trend(monthly))

    if fire:
        notes.append(f"Firefighting pattern: {len(fire)} matching revert/hotfix-style commits in the chosen window.")
    else:
        notes.append("Firefighting pattern: no matching revert/hotfix-style commits in the chosen window.")

    return notes


def pairs_to_objects(rows: list[tuple[str, int]], key: str) -> list[dict[str, str | int]]:
    return [{key: name, "count": count} for name, count in rows]


def build_report(
    root: pathlib.Path,
    since: str,
    authors_since: str,
    top: int,
    churn: list[tuple[str, int]],
    overall_authors: list[tuple[str, int]],
    recent_authors: list[tuple[str, int]],
    bugs: list[tuple[str, int]],
    monthly: list[tuple[str, int]],
    fire: list[str],
) -> dict[str, object]:
    bug_files = {path for path, _ in bugs}
    overlap = [path for path, _ in churn if path in bug_files]

    ownership: dict[str, object] | None = None
    if overall_authors:
        lead_author, lead_count = overall_authors[0]
        total_commits = sum(count for _, count in overall_authors)
        recent_names = {name for name, _ in recent_authors}
        ownership = {
            "lead_author": lead_author,
            "lead_commit_count": lead_count,
            "lead_share": round((lead_count / total_commits) if total_commits else 0.0, 4),
            "top_author_in_recent_window": lead_author in recent_names,
            "total_non_merge_commits": total_commits,
        }

    return {
        "title": "Repo History Triage",
        "repository": str(root),
        "windows": {
            "since": since,
            "recent_authors_since": authors_since,
        },
        "signals": risk_notes(churn, bugs, overall_authors, recent_authors, monthly, fire),
        "overlap_hotspots": overlap,
        "ownership": ownership,
        "delivery_trend": recent_trend(monthly),
        "firefighting_commit_count": len(fire),
        "tables": {
            "churn_hotspots": pairs_to_objects(churn[:top], "path"),
            "overall_contributors": pairs_to_objects(overall_authors[:top], "author"),
            "recent_contributors": pairs_to_objects(recent_authors[:top], "author"),
            "bug_hotspots": pairs_to_objects(bugs[:top], "path"),
            "commits_by_month": pairs_to_objects(monthly[-top:], "month"),
            "firefighting_commits": fire[:top],
        },
    }


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


def print_text_report(report: dict[str, object]) -> None:
    windows = report["windows"]
    tables = report["tables"]

    print(report["title"])
    print(f"Repository: {report['repository']}")
    print(f"Window: {windows['since']}")
    print(f"Recent authors window: {windows['recent_authors_since']}")

    print("\nSignals")
    for note in report["signals"]:
        print(f"  - {note}")

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
    parser.add_argument("--bug-pattern", default="fix|bug|broken", help="Case-insensitive regex for bug-fix commit messages.")
    parser.add_argument("--fire-pattern", default=r"revert|hotfix|emergency|rollback", help="Case-insensitive regex for firefighting commits.")
    args = parser.parse_args()

    try:
        root = repo_root(pathlib.Path(args.repo).resolve())
        churn = churn_hotspots(root, args.since, args.top)
        overall_authors = contributors(root)
        recent_authors = contributors(root, args.authors_since)
        bugs = bug_hotspots(root, args.since, args.bug_pattern, args.top)
        monthly = monthly_commits(root)
        fire = firefighting(root, args.since, args.fire_pattern)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr or str(exc))
        return exc.returncode or 1

    report = build_report(
        root=root,
        since=args.since,
        authors_since=args.authors_since,
        top=args.top,
        churn=churn,
        overall_authors=overall_authors,
        recent_authors=recent_authors,
        bugs=bugs,
        monthly=monthly,
        fire=fire,
    )

    if args.format == "json":
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print_text_report(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

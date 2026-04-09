from __future__ import annotations

import collections
import datetime as dt
import pathlib
import subprocess
from typing import Any


DEFAULT_BUG_PATTERN = r"(^|[^[:alnum:]_])(fix|fixed|fixes|bug|bugs|broken)([^[:alnum:]_]|$)"
LENS_ORDER = [
    ("changes_most", "What changes most"),
    ("who_built_this", "Who built this"),
    ("bugs_cluster", "Where bugs cluster"),
    ("delivery_trend", "Is the project accelerating or dying"),
    ("firefighting", "How often is the team firefighting"),
]


def git_command(repo: pathlib.Path, args: list[str]) -> list[str]:
    return ["git", "-C", str(repo), *args]


def run_git(repo: pathlib.Path, args: list[str]) -> str:
    result = subprocess.run(
        git_command(repo, args),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def git_result(repo: pathlib.Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        git_command(repo, args),
        check=False,
        capture_output=True,
        text=True,
    )


def repo_root(repo: pathlib.Path) -> pathlib.Path:
    output = run_git(repo, ["rev-parse", "--show-toplevel"]).strip()
    return pathlib.Path(output)


def has_commits(repo: pathlib.Path) -> bool:
    return git_result(repo, ["rev-parse", "--verify", "HEAD"]).returncode == 0


def count_lines(lines: list[str]) -> collections.Counter[str]:
    counter: collections.Counter[str] = collections.Counter()
    for line in lines:
        value = line.strip()
        if value:
            counter[value] += 1
    return counter


def limit_rows(rows: list[Any], top: int, *, tail: bool = False) -> list[Any]:
    if top <= 0:
        return []
    return rows[-top:] if tail else rows[:top]


def month_key_to_date(value: str) -> dt.date:
    return dt.date.fromisoformat(f"{value}-01")


def next_month(value: dt.date) -> dt.date:
    if value.month == 12:
        return dt.date(value.year + 1, 1, 1)
    return dt.date(value.year, value.month + 1, 1)


def fill_missing_months(counts: collections.Counter[str]) -> list[tuple[str, int]]:
    if not counts:
        return []

    months = sorted(counts)
    current = month_key_to_date(months[0])
    end = month_key_to_date(months[-1])
    series: list[tuple[str, int]] = []
    while current <= end:
        key = current.strftime("%Y-%m")
        series.append((key, counts.get(key, 0)))
        current = next_month(current)
    return series


def churn_hotspots(repo: pathlib.Path, since: str, top: int) -> list[tuple[str, int]]:
    raw = run_git(repo, ["log", "--format=format:", "--name-only", f"--since={since}"])
    return limit_rows(count_lines(raw.splitlines()).most_common(), top)


def contributors(repo: pathlib.Path, since: str | None = None) -> list[tuple[str, str, int]]:
    args = ["log", "--no-merges", "--format=%aE%x1f%aN%x1e"]
    if since:
        args.append(f"--since={since}")
    raw = run_git(repo, args)

    counts: collections.Counter[str] = collections.Counter()
    labels: dict[str, str] = {}
    for entry in raw.split("\x1e"):
        if not entry.strip():
            continue
        email, _, name = entry.partition("\x1f")
        email = email.strip().lower()
        name = name.strip()
        key = email or name.lower()
        if not key:
            continue
        counts[key] += 1
        if key not in labels:
            labels[key] = name or email or key

    rows = [(key, labels.get(key, key), count) for key, count in counts.items()]
    rows.sort(key=lambda row: (-row[2], row[1].lower(), row[0]))
    return rows


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
    return limit_rows(count_lines(raw.splitlines()).most_common(), top)


def monthly_commits(repo: pathlib.Path) -> list[tuple[str, int]]:
    raw = run_git(repo, ["log", "--format=%ad", "--date=format:%Y-%m"])
    return fill_missing_months(count_lines(raw.splitlines()))


def firefighting(repo: pathlib.Path, since: str, pattern: str) -> list[str]:
    raw = run_git(repo, ["log", "--oneline", f"--since={since}"])
    matched = run_git(repo, ["log", "--oneline", "-i", "-E", f"--grep={pattern}", f"--since={since}"])
    matches = {line.strip() for line in matched.splitlines() if line.strip()}
    return [line for line in raw.splitlines() if line.strip() in matches]


def make_lens(
    status: str,
    severity: str,
    confidence: str,
    summary: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": status,
        "severity": severity,
        "confidence": confidence,
        "summary": summary,
        "evidence": evidence,
    }


def changes_lens(churn: list[tuple[str, int]], has_history_flag: bool) -> dict[str, Any]:
    if not has_history_flag:
        return make_lens(
            "unknown",
            "low",
            "low",
            "No commit history yet; churn hotspots are unavailable.",
            {"top_path": None, "top_count": 0, "total_touches": 0},
        )
    if not churn:
        return make_lens(
            "quiet",
            "low",
            "low",
            "No churn hotspots were detected in the selected window.",
            {"top_path": None, "top_count": 0, "total_touches": 0},
        )

    total_touches = sum(count for _, count in churn)
    top_path, top_count = churn[0]
    share = (top_count / total_touches) if total_touches else 0.0
    severity = "high" if share >= 0.5 else "medium" if share >= 0.25 else "low"
    confidence = "high" if total_touches >= 10 else "medium"
    return make_lens(
        "hotspot",
        severity,
        confidence,
        f"{top_path} is the main churn hotspot ({top_count} touches, {share:.0%} of sampled file changes).",
        {
            "top_path": top_path,
            "top_count": top_count,
            "top_share": round(share, 4),
            "total_touches": total_touches,
        },
    )


def ownership_lens(
    overall_authors: list[tuple[str, str, int]],
    recent_authors: list[tuple[str, str, int]],
    has_history_flag: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not has_history_flag or not overall_authors:
        return (
            make_lens(
                "unknown",
                "low",
                "low",
                "No author history is available yet.",
                {
                    "lead_author": None,
                    "lead_share": 0.0,
                    "total_non_merge_commits": 0,
                    "recent_contributor_count": 0,
                },
            ),
            None,
        )

    lead_key, lead_author, lead_count = overall_authors[0]
    total_commits = sum(count for _, _, count in overall_authors)
    lead_share = (lead_count / total_commits) if total_commits else 0.0
    recent_keys = {key for key, _, _ in recent_authors}
    lead_recent = lead_key in recent_keys

    status = "concentrated" if lead_share >= 0.6 else "distributed"
    if lead_share >= 0.75 or (lead_share >= 0.6 and not lead_recent):
        severity = "high"
    elif lead_share >= 0.6 or not lead_recent:
        severity = "medium"
    else:
        severity = "low"
    confidence = "high" if total_commits >= 5 else "medium"

    if lead_share >= 0.6 and not lead_recent:
        summary = (
            f"Ownership is concentrated around {lead_author} ({lead_share:.0%} of non-merge commits), "
            "but that lead contributor is absent from the recent window."
        )
    elif lead_share >= 0.6:
        summary = f"Ownership is concentrated around {lead_author} ({lead_share:.0%} of non-merge commits)."
    elif not lead_recent:
        summary = (
            f"Ownership is more distributed overall, but the historical lead contributor {lead_author} "
            "is absent from the recent window."
        )
    else:
        summary = f"Ownership looks relatively distributed; {lead_author} leads with {lead_share:.0%} of non-merge commits."

    ownership = {
        "lead_author": lead_author,
        "lead_commit_count": lead_count,
        "lead_share": round(lead_share, 4),
        "top_author_in_recent_window": lead_recent,
        "total_non_merge_commits": total_commits,
    }
    return (
        make_lens(
            status,
            severity,
            confidence,
            summary,
            {
                **ownership,
                "recent_contributor_count": len(recent_authors),
                "overall_contributor_count": len(overall_authors),
            },
        ),
        ownership,
    )


def bug_lens(
    bugs: list[tuple[str, int]],
    overlap: list[str],
    has_history_flag: bool,
) -> dict[str, Any]:
    if not has_history_flag:
        return make_lens(
            "unknown",
            "low",
            "low",
            "No commit history yet; bug-hotspot heuristics are unavailable.",
            {"overlap_count": 0, "bug_hotspot_count": 0, "top_bug_path": None},
        )
    if overlap:
        return make_lens(
            "overlap_detected",
            "high",
            "medium",
            f"Bug-fix activity overlaps with churn hotspots in {', '.join(overlap[:3])}.",
            {
                "overlap_count": len(overlap),
                "overlap_paths": overlap[:5],
                "bug_hotspot_count": len(bugs),
                "top_bug_path": bugs[0][0] if bugs else None,
            },
        )
    if bugs:
        top_bug_path, top_bug_count = bugs[0]
        return make_lens(
            "active",
            "medium",
            "low",
            f"Bug-fix commit keywords point to {top_bug_path} ({top_bug_count} matching touches), but no churn overlap was detected.",
            {
                "overlap_count": 0,
                "bug_hotspot_count": len(bugs),
                "top_bug_path": top_bug_path,
                "top_bug_count": top_bug_count,
            },
        )
    return make_lens(
        "quiet",
        "low",
        "low",
        "No bug hotspots were detected from commit-message keywords.",
        {"overlap_count": 0, "bug_hotspot_count": 0, "top_bug_path": None},
    )


def delivery_lens(monthly: list[tuple[str, int]], has_history_flag: bool) -> dict[str, Any]:
    if not has_history_flag:
        return make_lens(
            "unknown",
            "low",
            "low",
            "No commits yet; insufficient history for a trend call.",
            {"recent_average": 0.0, "previous_average": 0.0, "months_considered": 0},
        )
    if len(monthly) < 9:
        return make_lens(
            "unknown",
            "low",
            "low",
            "Insufficient monthly history for a trend call.",
            {"recent_average": 0.0, "previous_average": 0.0, "months_considered": len(monthly)},
        )

    recent = [count for _, count in monthly[-3:]]
    previous = [count for _, count in monthly[-9:-3]]
    recent_avg = sum(recent) / len(recent)
    previous_avg = sum(previous) / len(previous)
    evidence = {
        "recent_average": round(recent_avg, 2),
        "previous_average": round(previous_avg, 2),
        "recent_months": [month for month, _ in monthly[-3:]],
        "previous_months": [month for month, _ in monthly[-9:-3]],
        "months_considered": len(monthly),
    }

    if recent_avg == 0 and previous_avg == 0:
        return make_lens(
            "quiet",
            "low",
            "medium",
            "There has been no commit activity across the last nine calendar months.",
            evidence,
        )
    if previous_avg == 0:
        return make_lens(
            "accelerating",
            "medium",
            "medium",
            f"Recent commit volume picked up to {recent_avg:.1f}/month after a quiet prior six-month baseline.",
            evidence,
        )
    if recent_avg <= previous_avg * 0.6:
        status = "quiet" if recent_avg == 0 else "declining"
        severity = "high" if recent_avg == 0 else "medium"
        return make_lens(
            status,
            severity,
            "high",
            f"Recent commit volume is down ({recent_avg:.1f}/month vs {previous_avg:.1f}/month across the prior six months).",
            evidence,
        )
    if recent_avg >= previous_avg * 1.4:
        return make_lens(
            "accelerating",
            "medium",
            "high",
            f"Recent commit volume is up ({recent_avg:.1f}/month vs {previous_avg:.1f}/month across the prior six months).",
            evidence,
        )
    return make_lens(
        "steady",
        "low",
        "high",
        f"Commit volume looks roughly steady ({recent_avg:.1f}/month vs {previous_avg:.1f}/month across the prior six months).",
        evidence,
    )


def firefighting_lens(fire: list[str], has_history_flag: bool, since: str) -> dict[str, Any]:
    if not has_history_flag:
        return make_lens(
            "unknown",
            "low",
            "low",
            "No commit history yet; firefighting heuristics are unavailable.",
            {"matching_commit_count": 0, "window": since, "sample_commits": []},
        )
    count = len(fire)
    if count == 0:
        return make_lens(
            "quiet",
            "low",
            "medium",
            "No revert/hotfix-style commits matched in the selected window.",
            {"matching_commit_count": 0, "window": since, "sample_commits": []},
        )

    severity = "high" if count >= 5 else "medium" if count >= 2 else "low"
    return make_lens(
        "active",
        severity,
        "medium",
        f"{count} revert/hotfix-style commit(s) matched in the selected window.",
        {"matching_commit_count": count, "window": since, "sample_commits": fire[:3]},
    )


def build_lens_summary(
    churn: list[tuple[str, int]],
    bugs: list[tuple[str, int]],
    overall_authors: list[tuple[str, str, int]],
    recent_authors: list[tuple[str, str, int]],
    monthly: list[tuple[str, int]],
    fire: list[str],
    since: str,
    has_history_flag: bool,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None, list[str]]:
    bug_files = {path for path, _ in bugs}
    overlap = [path for path, _ in churn if path in bug_files]
    ownership_summary, ownership = ownership_lens(overall_authors, recent_authors, has_history_flag)
    lens_summary = {
        "changes_most": changes_lens(churn, has_history_flag),
        "who_built_this": ownership_summary,
        "bugs_cluster": bug_lens(bugs, overlap, has_history_flag),
        "delivery_trend": delivery_lens(monthly, has_history_flag),
        "firefighting": firefighting_lens(fire, has_history_flag, since),
    }
    return lens_summary, ownership, overlap


def contributor_objects(rows: list[tuple[str, str, int]]) -> list[dict[str, str | int]]:
    return [{"author": label, "count": count} for _, label, count in rows]


def pairs_to_objects(rows: list[tuple[str, int]], key: str) -> list[dict[str, str | int]]:
    return [{key: name, "count": count} for name, count in rows]


def collect_report_data(
    root: pathlib.Path,
    since: str,
    authors_since: str,
    top: int,
    bug_pattern: str,
    fire_pattern: str,
) -> dict[str, Any]:
    history_present = has_commits(root)
    if history_present:
        churn = churn_hotspots(root, since, top)
        overall_authors = contributors(root)
        recent_authors = contributors(root, authors_since)
        bugs = bug_hotspots(root, since, bug_pattern, top)
        monthly = monthly_commits(root)
        fire = firefighting(root, since, fire_pattern)
    else:
        churn = []
        overall_authors = []
        recent_authors = []
        bugs = []
        monthly = []
        fire = []

    lens_summary, ownership, overlap = build_lens_summary(
        churn=churn,
        bugs=bugs,
        overall_authors=overall_authors,
        recent_authors=recent_authors,
        monthly=monthly,
        fire=fire,
        since=since,
        has_history_flag=history_present,
    )
    return {
        "title": "Repo History Triage",
        "repository": str(root),
        "windows": {"since": since, "recent_authors_since": authors_since},
        "signals": [lens_summary[key]["summary"] for key, _ in LENS_ORDER],
        "lens_summary": lens_summary,
        "overlap_hotspots": overlap,
        "ownership": ownership,
        "delivery_trend": lens_summary["delivery_trend"]["summary"],
        "firefighting_commit_count": len(fire),
        "tables": {
            "churn_hotspots": pairs_to_objects(limit_rows(churn, top), "path"),
            "overall_contributors": contributor_objects(limit_rows(overall_authors, top)),
            "recent_contributors": contributor_objects(limit_rows(recent_authors, top)),
            "bug_hotspots": pairs_to_objects(limit_rows(bugs, top), "path"),
            "commits_by_month": pairs_to_objects(limit_rows(monthly, top, tail=True), "month"),
            "firefighting_commits": limit_rows(fire, top),
        },
    }

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills/repo-history-triage/scripts/repo_history_triage.py"
LENS_KEYS = {
    "changes_most",
    "who_built_this",
    "bugs_cluster",
    "delivery_trend",
    "firefighting",
}


class RepoHistoryTriageCliTests(unittest.TestCase):
    maxDiff = None

    def _invoke(self, repo: Path, *extra_args: str, format: str = "json") -> subprocess.CompletedProcess[str]:
        args = [
            sys.executable,
            str(SCRIPT_PATH),
            "--repo",
            str(repo),
            "--since",
            "1970-01-01",
            "--authors-since",
            "1970-01-01",
            "--top",
            "40",
            "--format",
            format,
            *extra_args,
        ]
        return subprocess.run(args, capture_output=True, text=True, check=False)

    def _git(self, repo: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=True,
            env=full_env,
        )

    def _init_repo(self) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        repo = Path(tmpdir.name) / "repo"
        repo.mkdir()
        self._git(repo, "init", "-q")
        return repo

    def _commit(
        self,
        repo: Path,
        filename: str,
        contents: str,
        message: str,
        author_name: str,
        author_email: str,
        date: str,
    ) -> None:
        path = repo / filename
        path.write_text(contents, encoding="utf-8")
        self._git(repo, "add", filename)
        self._git(
            repo,
            "commit",
            "-q",
            "-m",
            message,
            env={
                "GIT_AUTHOR_NAME": author_name,
                "GIT_AUTHOR_EMAIL": author_email,
                "GIT_AUTHOR_DATE": date,
                "GIT_COMMITTER_NAME": author_name,
                "GIT_COMMITTER_EMAIL": author_email,
                "GIT_COMMITTER_DATE": date,
            },
        )

    def _json(self, repo: Path, *extra_args: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        result = self._invoke(repo, *extra_args, format="json")
        return result, json.loads(result.stdout)

    def test_empty_repo_returns_structured_json_exit_zero(self) -> None:
        repo = self._init_repo()

        result, report = self._json(repo)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["title"], "Repo History Triage")
        self.assertIsNone(report["ownership"])
        self.assertEqual(report["tables"]["overall_contributors"], [])
        self.assertEqual(report["tables"]["commits_by_month"], [])
        self.assertEqual(set(report["lens_summary"]), LENS_KEYS)
        self.assertEqual(report["lens_summary"]["changes_most"]["confidence"], "low")
        self.assertIn("No commits yet", report["delivery_trend"])

    def test_sparse_history_fills_zero_months_and_reports_decline(self) -> None:
        repo = self._init_repo()
        dates = [
            "2024-01-15T12:00:00+0000",
            "2024-02-15T12:00:00+0000",
            "2024-03-15T12:00:00+0000",
            "2024-04-15T12:00:00+0000",
            "2024-05-15T12:00:00+0000",
            "2024-06-15T12:00:00+0000",
            "2024-09-15T12:00:00+0000",
        ]
        for index, date in enumerate(dates, start=1):
            self._commit(
                repo,
                f"file-{index}.txt",
                f"{index}\n",
                f"change {index}",
                "Mahesh Rijal",
                "mahesh@example.com",
                date,
            )

        _, report = self._json(repo)
        commits_by_month = report["tables"]["commits_by_month"]

        self.assertTrue(any(row["month"] == "2024-07" and row["count"] == 0 for row in commits_by_month))
        self.assertTrue(any(row["month"] == "2024-08" and row["count"] == 0 for row in commits_by_month))
        self.assertEqual(report["lens_summary"]["delivery_trend"]["status"], "declining")
        self.assertNotIn("roughly steady", report["delivery_trend"])

    def test_same_email_merges_contributor_names(self) -> None:
        repo = self._init_repo()
        self._commit(
            repo,
            "alpha.txt",
            "alpha\n",
            "first change",
            "Mahesh Rijal",
            "mahesh@example.com",
            "2024-01-15T12:00:00+0000",
        )
        self._commit(
            repo,
            "beta.txt",
            "beta\n",
            "second change",
            "maheshrijal",
            "mahesh@example.com",
            "2024-02-15T12:00:00+0000",
        )

        _, report = self._json(repo)
        contributors = report["tables"]["overall_contributors"]

        self.assertEqual(len(contributors), 1)
        self.assertEqual(contributors[0]["author"], "maheshrijal")
        self.assertEqual(contributors[0]["count"], 2)
        self.assertEqual(report["ownership"]["lead_commit_count"], 2)

    def test_default_bug_pattern_ignores_prefix_and_debug(self) -> None:
        repo = self._init_repo()
        commits = [
            ("prefix.txt", "prefix\n", "prefix pipeline cleanup", "2024-01-15T12:00:00+0000"),
            ("debug.txt", "debug\n", "debug logging cleanup", "2024-02-15T12:00:00+0000"),
            ("fix.txt", "fix\n", "fix issue", "2024-03-15T12:00:00+0000"),
            ("broken.txt", "broken\n", "broken build", "2024-04-15T12:00:00+0000"),
        ]
        for filename, contents, message, date in commits:
            self._commit(repo, filename, contents, message, "Mahesh Rijal", "mahesh@example.com", date)

        _, report = self._json(repo)
        bug_paths = {row["path"] for row in report["tables"]["bug_hotspots"]}

        self.assertEqual(bug_paths, {"fix.txt", "broken.txt"})
        self.assertEqual(report["lens_summary"]["bugs_cluster"]["status"], "overlap_detected")

    def test_json_includes_lens_summary_with_five_keys(self) -> None:
        repo = self._init_repo()
        self._commit(
            repo,
            "one.txt",
            "alpha\n",
            "initial change",
            "Mahesh Rijal",
            "mahesh@example.com",
            "2024-01-15T12:00:00+0000",
        )

        _, report = self._json(repo)
        lens_summary = report["lens_summary"]

        self.assertEqual(set(lens_summary), LENS_KEYS)
        for lens in lens_summary.values():
            self.assertIn("status", lens)
            self.assertIn("severity", lens)
            self.assertIn("confidence", lens)
            self.assertIn("summary", lens)
            self.assertIn("evidence", lens)

    def test_text_output_shows_overview_before_tables(self) -> None:
        repo = self._init_repo()
        self._commit(
            repo,
            "one.txt",
            "alpha\n",
            "initial change",
            "Mahesh Rijal",
            "mahesh@example.com",
            "2024-01-15T12:00:00+0000",
        )

        result = self._invoke(repo, format="text")
        output = result.stdout

        self.assertEqual(result.returncode, 0)
        self.assertIn("Five-Lens Overview", output)
        self.assertLess(output.index("Five-Lens Overview"), output.index("Churn Hotspots"))


if __name__ == "__main__":
    unittest.main()

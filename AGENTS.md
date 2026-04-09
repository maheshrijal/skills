# AGENTS.md

## Repo Notes

- Keep developer-only verification guidance out of skill-facing docs like `SKILL.md`.
- For `repo-history-triage`, run `python3 -m unittest discover -s tests` before shipping changes.
- Local fixtures should cover empty repositories, sparse histories with zero-commit month gaps, contributor aliasing by shared email, and bug-keyword false positives.

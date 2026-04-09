---
name: repo-history-triage
description: Analyze Git repository history to surface churn hotspots, ownership concentration, bug-prone files, delivery momentum, and firefighting patterns. Use when assessing repository health, auditing engineering risk, planning a refactor, investigating instability, reviewing a handoff, or understanding maintenance patterns in an unfamiliar codebase.
---

# Repo History Triage

Analyze repository history through five lenses: what changes most, who built it, where bugs cluster, whether delivery is accelerating or stalling, and how often the team is firefighting.

## Workflow

1. Confirm the repository root.
2. Run the helper in structured mode first:

```bash
python3 scripts/repo_history_triage.py --repo /path/to/repo --format json
```

This returns a machine-readable `lens_summary` with one structured summary per review lens, alongside the hotspot tables.

3. If the result needs more human-readable detail, rerun in text mode:

```bash
python3 scripts/repo_history_triage.py \
  --repo /path/to/repo \
  --since "18 months ago" \
  --authors-since "9 months ago" \
  --top 15
```

4. Synthesize the output. Do not stop at raw tables.

## Five-Lens Review

### 1. What Changes Most

Treat high-churn files as maintenance pressure, not automatic defects.

- If a file dominates the churn table, explain whether it looks like active development, configuration drift, or chronic instability.
- If a hotspot is a workflow file, README, changelog, or generated config, say that plainly and lower its risk weight.

### 2. Who Built This

Read authorship as ownership concentration and continuity risk.

- If one author holds roughly 60% or more of commits, call out concentration.
- If the historical lead is missing from the recent window, call out continuity risk.
- If many historical contributors exist but only a few are still active, call out maintenance handoff risk.
- If squash-merge workflows likely flatten authorship, state that the signal may reflect mergers rather than original authors.

### 3. Where Bugs Cluster

Compare bug hotspots to churn hotspots.

- Files that appear on both lists are highest-value investigation targets.
- If bug hotspots are mostly docs, release files, or CI metadata, say the commit-message heuristic is noisy.
- Treat this signal as directional when commit messages are weak or generic.

### 4. Is The Project Accelerating Or Dying

Read commit cadence as team/process data, not code quality.

- Steady monthly output suggests consistent delivery.
- A sharp drop can indicate staffing loss, release freeze, or reduced investment.
- Spikes followed by quiet periods can suggest batch releases or crunch-driven work.
- If the repo is too new or history is too short, say the trend signal is weak.

### 5. How Often Is The Team Firefighting

Interpret revert, hotfix, emergency, and rollback commits as delivery confidence signals.

- A few over a year can be normal.
- Frequent matches suggest weak tests, risky deploys, missing staging confidence, or rollback-heavy operations.
- Zero matches can mean stability or vague commit messages. Say which seems more likely.

## Output Contract

Always return a concise, high-impact review in this order:

1. `Executive Summary`
   - 2-4 bullets
   - strongest conclusions only
   - explain what the history implies about code risk and team/process risk

2. `Five-Lens Review`
   - `What changes most`
   - `Who built this`
   - `Where bugs cluster`
   - `Is the project accelerating or dying`
   - `How often is the team firefighting`
   - for each lens: state the signal, then the implication

3. `Priority Targets`
   - specific files or directories to inspect next
   - reason each target matters

4. `Questions To Ask`
   - ownership gaps
   - test/deploy confidence
   - release process
   - commit hygiene or merge strategy caveats

5. `Caveats`
   - weak commit-message discipline
   - squash merges
   - short or unusually bursty history
   - metadata files dominating results

## Success Criteria

- Translate the five signals into an executive review, not a command transcript.
- Reflect the five-lens framework above in the summary.
- Distinguish code risk from team/process risk.
- Lower confidence when the evidence is weak.
- Name the first files or directories worth deeper inspection.

## Guardrails

- Prefer `--format json` for synthesis.
- Use text output only when you need human-readable tables.
- Do not treat churn alone as proof of bad code.
- Do not overfit to commit-message keywords without noting their limits.
- If the history is sparse, say so plainly and fall back to direct code reading.

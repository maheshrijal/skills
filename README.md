# skills

Curated Agent Skills collection.

## Layout

Skills live under `skills/<skill-name>/`.

## Install with npx

```bash
# List skills in this repo
npx skills add maheshrijal/skills --list

# Install a specific skill from GitHub
npx skills add maheshrijal/skills --skill repo-history-triage

# Install from the full GitHub URL
npx skills add https://github.com/maheshrijal/skills --skill repo-history-triage

# Install every skill in this repo
npx skills add maheshrijal/skills --skill '*'

# Install non-interactively to the global skill directory
npx skills add maheshrijal/skills --skill repo-history-triage --global --yes
```

## Available Skills

Currently this repo contains 1 skill:

- `repo-history-triage`: Analyze Git repository history to surface churn hotspots, ownership concentration, bug-prone files, delivery momentum, and firefighting patterns.

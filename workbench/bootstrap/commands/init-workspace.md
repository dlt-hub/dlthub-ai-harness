---
name: init-workspace
description: Sets up dlthub workspace. Ensures `uv`, Python env and dlt are present. Installs LLM toolkit to kickstart future work.
---

# Initialize dlt workspace

Makes sure that `uv`, Python `venv` and `dlt` is installed, then sets up AI support.

## Step 1: Gather evidence

Run all checks **silently** — do NOT install or change anything yet. Execute in order! If previous check does not work - others
will not work as well.

1. `uv --version` — is uv installed?
2. `ls .venv/` — does a venv exist?
3. `uv run dlt --version` — is dlt installed in the venv?

## Step 2: Present plan

Show the user what was found and what needs to be done:

```
Workspace status:
  uv:    ✓ installed (x.y.z) / ✗ not found
  venv:  ✓ exists (.venv/) / ✗ missing
  dlt:   ✓ installed (x.y.z) / ✗ not found

Actions needed:
  1. Install uv          (if missing)
  2. Create venv         (if missing)
  3. Install dlt         (if missing)
```

If everything is already set up, say so and skip to the report. Otherwise, ask the user to confirm before proceeding.

## Step 3: Execute

Only after user confirms, run the needed actions:

**Install uv** (if missing):
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Create venv** (if missing):
```
uv venv
```

**Install dlt** (if missing or outdated):
```
uv pip install --upgrade dlt[workspace]==1.23.0a3
```

This installs (or upgrades) dlt with marimo, ibis, and other workspace tools.
**Note**: - if adding `dlt` to `pyproject.toml` you must pin the exact installed version (`==`) — `uv add` may downgrade pre-release versions


## Step 4: AI init and report

1. Setup essential skills and rules from dlthub init toolkit:
```
uv run dlt --non-interactive ai init
```

2. Show ai setup info
```
uv run dlt ai status
```

NOTE: WARNING that mcp cannot be started is most probably a result of missing dependencies. Help user
to solve it before proceeding.

3. Show available toolkits
```
uv run dlt ai toolkit list
```

3. Tell user:
* To restart the session **NOW** so mcp server can run and skills are visible.
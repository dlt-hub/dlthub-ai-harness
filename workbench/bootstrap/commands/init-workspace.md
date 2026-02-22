---
name: init-workspace
description: Sets up dlthub workspace. Ensures `uv`, Python env and dlt are present. Installs LLM toolkit to kickstart future work.
---

# Initialize dlt workspace

Makes sure that `uv`, Python `venv` and `dlt` is installed, then sets up AI support.

## Phase 1: Gather evidence

Run all checks **silently** — do NOT install or change anything yet. Execute in order! If previous check does not work - others
will not work as well.

1. `uv --version` — is uv installed?
2. `ls .venv/` — does a venv exist?
3. `uv run dlt --version` — is dlt installed in the venv?
4. `ls .dlt/` — does a dlt workspace exist?

## Phase 2: Present plan

Show the user what was found and what needs to be done:

```
Workspace status:
  uv:    ✓ installed (x.y.z) / ✗ not found
  venv:  ✓ exists (.venv/) / ✗ missing
  dlt:   ✓ installed (x.y.z) / ✗ not found
  .dlt:  ✓ exists / ✗ not yet (created by dlt init)

Actions needed:
  1. Install uv          (if missing)
  2. Create venv         (if missing)
  3. Install dlt         (if missing)
```

If everything is already set up, say so and skip to the report. Otherwise, ask the user to confirm before proceeding.

## Phase 3: Execute

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
uv pip install --upgrade --pre dlt[workspace]
```

This installs (or upgrades) dlt with marimo, ibis, and other workspace tools. `--pre` allows alpha/pre-release versions.

## Phase 4: AI init

Setup essential skills and rules from dlthub init toolkit:
```
uv run dlt ai init
```

Use `dlt ai toolkit list` to list AI assisted workflows.

## Phase 5: Report

```
Workspace ready:
- Python: <version>
- uv: <version>
- dlt: <version>
- venv: .venv/
```
Offer next steps: `dlt ai toolkit list` to list AI assisted workflows. **pick only pipeline building workflows**


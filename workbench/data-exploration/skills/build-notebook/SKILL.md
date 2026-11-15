---
name: build-notebook
argument-hint: "[spec-path]"
description: "Use when the user wants to build, launch or regenerate the marimo notebook or dashboard from an analysis_plan.md, or open the charts they planned. Renders the planned charts into a marimo app and starts it. Not for planning charts (explore-data)."
---

# Build notebook from spec

Read the analysis plan `.dlthub/explorations/<pipeline_name>/analysis_plan.md` and assemble a marimo notebook with all charts.

Parse `$ARGUMENTS`:
- `spec-path` (optional): path to the analysis plan. If omitted, use the plan of the pipeline in session context, or list `.dlthub/explorations/*/analysis_plan.md`. If several plans exist and the pipeline is not known, ask the user and stop.

## Step 1: Read analysis_plan.md

Parse the analysis plan file for:
- **Connection** section: pipeline name, module, destination and dataset name
- **Chart N** sections: each chart's question, type, SQL code, and altair code
- Count the total number of charts to assemble

If the analysis plan file is missing or has no charts, tell the user to run `explore-data` first and stop.

## Step 2: Assemble notebook

The dashboard is the user's code. Take its path from the `## Dashboard` section of the plan. If the section is empty, propose a path, for example `<pipeline_name>_dashboard.py` in the project root, ask the user, and write the chosen path into the plan. Below, `<dashboard>` is that path.

Generate `<dashboard>`. Read `references/notebook-patterns.md` for the complete notebook structure, cell templates, and naming conventions before generating. Every chart cell must end with `_chart` on a bare line, then `return` — without the bare expression line, nothing renders.

## Marimo patterns

For general marimo cell structure, reactivity, and best practices, fetch https://github.com/marimo-team/skills/blob/main/skills/marimo-notebook/SKILL.md. For SQL-specific patterns in marimo, fetch https://github.com/marimo-team/skills/blob/main/skills/marimo-notebook/references/SQL.md. For dlt-dashboard-specific templates, see `references/notebook-patterns.md`.

## Step 3: Validate

Run marimo's linter to catch common mistakes:

```bash
uvx marimo check <dashboard>
```

If validation fails:
1. Read the error output — marimo check reports specific issues (missing returns, variable conflicts, import errors).
2. Fix the reported issues in the notebook file.
3. Re-run `uvx marimo check` until it passes.

## Step 4: Ensure dependencies

The notebook requires `pandas`, `numpy`, and `altair` which are **not** installed by `dlt` or `dlthub`. A workspace created by `uvx dlthub-init@latest` may already declare them in `pyproject.toml` — then `uv sync` installs them.

Before launching, check if they are available. If any are missing, **ask the user** how they want to install them:

- If they are declared in `pyproject.toml` (workspace scaffolded by `dlthub init`): run `uv sync`.
- Otherwise: run `uv add pandas numpy altair` to add them to `pyproject.toml`.

Also add `marimo` if not already installed, and `ibis-framework[duckdb]` if any chart uses ibis.

**Do NOT install packages without user confirmation.**

## Step 5: Launch

After validation passes, offer to launch in browser or skip.

If yes:
```bash
uv run marimo edit <dashboard> --no-token
```

Tell the user the notebook is running (default: localhost:2718).

## Regeneration

When re-invoked after iteration (see `workflow.md`): re-read the full analysis_plan.md and regenerate the entire notebook file, then validate and relaunch.

## Troubleshooting

### marimo check fails with variable conflicts
Two cells export the same variable name. Fix: follow the naming conventions in `references/notebook-patterns.md`.

### marimo check fails with import errors
A dependency is missing from the environment. Install it with `uv add <package>` and re-check.

### Notebook runs but charts are empty
The SQL query returns no rows. Common causes:
1. Filter is too restrictive — check `where` clauses.
2. Column names don't match schema — verify against `get_table_schema`.
3. Table is empty — check `get_row_counts` (MCP).

### The connection cell fails
- The import fails: the module in `## Connection` moved, or no longer creates the pipeline at the module level.
- A table is missing: the name, destination or dataset name differs from the pipeline that loaded the data, or the
  pipeline has not run with the active profile. Compare with `dlthub local pipeline info <name>`.

## Example

**Input:** `.dlthub/explorations/orders_pipeline/analysis_plan.md` with 2 charts (Monthly Revenue Trend + Revenue by Category); the user chose `orders_pipeline_dashboard.py` as the dashboard path.

**Output:** `orders_pipeline_dashboard.py` with 2 data cells + 2 chart cells, structured per `references/notebook-patterns.md`.

**Validation:** `uvx marimo check orders_pipeline_dashboard.py` → passes
**Launch:** `uv run marimo edit orders_pipeline_dashboard.py --no-token`

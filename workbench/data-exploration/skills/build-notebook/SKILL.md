---
name: build-notebook
argument-hint: "[spec-path]"
description: This skill should be used when the user asks to "build the notebook", "launch the dashboard", "generate the marimo notebook", or when an analysis_plan.md artifact exists and the user wants to assemble or regenerate the dashboard. Reads chart specs with ibis queries and altair code from analysis_plan.md, assembles a marimo Python file, validates, and launches. Do NOT use for exploring data or planning charts (use explore-data), building pipelines (use rest-api-pipeline toolkit), or deploying (use dlthub-platform toolkit).
---

# Build notebook from spec

Read a `<date>_<pipeline_name>_analysis_plan.md` artifact and assemble a marimo notebook with all charts.

Parse `$ARGUMENTS`:
- `spec-path` (optional): path to the analysis_plan.md file. If omitted, look for `*_analysis_plan.md` in the working directory. If multiple found, ask the user and stop.

## Step 1: Read analysis_plan.md

Parse the analysis plan file for:
- **Connection** section: pipeline name, dataset name, destination type
- **Chart N** sections: each chart's question, type, SQL code, and altair code
- Count the total number of charts to assemble

If the analysis plan file is missing or has no charts, tell the user to run `explore-data` first and stop.

## Step 2: Assemble notebook

Generate the **entire** `<pipeline_name>_dashboard.py` — all charts from analysis_plan.md — in **one Write call**. Read `references/notebook-patterns.md` for the complete notebook structure, cell templates, and naming conventions before generating; it has everything needed for a dlt dashboard. Every chart cell must end with `_chart` on a bare line, then `return` — without the bare expression line, nothing renders.

Do not fetch external marimo docs for a normal dashboard — `references/notebook-patterns.md` is sufficient. Only if a chart needs reactive UI elements not covered there, consult the marimo skill (https://github.com/marimo-team/skills/blob/main/skills/marimo-notebook/SKILL.md).

## Step 3: Validate

`marimo check` is a **static** linter (AST only — it does not launch a kernel or run cells). Run it once, batched with the dependency check, against the project venv:

```bash
uv run marimo check <pipeline_name>_dashboard.py
```

If validation fails: read **all** reported issues (missing returns, variable conflicts, import errors), fix them in a **single** edit pass, then re-run `marimo check` **once** to confirm. Do not loop check→fix→check one issue at a time — the generated file is fully known, so one corrective pass should clear it.

## Step 4: Ensure dependencies

The notebook requires `pandas`, `numpy`, and `altair` which are **not** installed by `dlt[hub]`. In a dlthub workspace (`dlthub init`) they are already declared in `pyproject.toml` — running `uv sync` installs them.

Before launching, check if they are available. If any are missing, **ask the user** how they want to install them:

- If they are declared in `pyproject.toml` (workspace scaffolded by `dlthub init`): run `uv sync`.
- Otherwise: run `uv add pandas numpy altair` to add them to `pyproject.toml`.

Also add `marimo` if not already installed, and `ibis-framework[duckdb]` if any chart uses ibis.

When you do run `uv sync`, chain the validation onto it in one call — `uv sync && uv run marimo check <pipeline_name>_dashboard.py` — to save a round-trip.

**Do NOT install packages without user confirmation.**

## Step 5: Run the whole notebook end-to-end

`marimo check` (Step 3) is static — it never executes the SQL or builds the charts. A marimo notebook is a runnable Python script (`app.run()` under `if __name__ == "__main__"`), so just run the file to execute every cell and catch runtime errors (bad column names, empty results, type mismatches) that static analysis misses:

```bash
uv run python <pipeline_name>_dashboard.py
```

A non-zero exit or traceback means a cell failed. If it fails, read all errors, fix in one edit pass, and re-run **once**. This step is the real proof the dashboard works — do it in headless runs too.

## Step 6: Launch as an app

Serve the notebook as a read-only app (runs all cells, hides the code):

```bash
uv run marimo run <pipeline_name>_dashboard.py --no-token
```

`marimo run` is a long-running server — start it in the **background** and report the URL (default: localhost:2718) immediately. **Do not** `sleep`/`cat`/poll its output waiting for "ready"; that just burns time. For an editable session instead of the read-only app, use `uv run marimo edit <pipeline_name>_dashboard.py --no-token`.

## Regeneration

When re-invoked after iteration (see `workflow.md`): re-read the full analysis_plan.md and regenerate the entire notebook file in one Write, then validate once. Relaunch only if the user is running it interactively.

## Troubleshooting

### marimo check fails with variable conflicts
Two cells export the same variable name. Fix: follow the naming conventions in `references/notebook-patterns.md`.

### marimo check fails with import errors
A dependency is missing from the environment. Install it with `uv add <package>` and re-check.

### Notebook runs but charts are empty
The SQL query returns no rows. Common causes:
1. Filter is too restrictive — check `where` clauses.
2. Column names don't match schema — verify against the schema already in context from `explore-data` (`export_schema` / `profile_tables` output); only if missing, make one `export_schema` call.
3. Table is empty — check `row_counts`.

### dlt.attach fails in notebook
Pipeline name is wrong or pipeline hasn't been run. Run `dlthub local pipeline info <name>` to verify.

## Example

**Input:** `2026-03-10_orders_pipeline_analysis_plan.md` with 2 charts (Monthly Revenue Trend + Revenue by Category)

**Output:** `orders_pipeline_dashboard.py` with 2 data cells + 2 chart cells, structured per `references/notebook-patterns.md`.

**Validation:** `uv run marimo check orders_pipeline_dashboard.py` → passes
**Launch (interactive only):** `uv run marimo edit orders_pipeline_dashboard.py --no-token`

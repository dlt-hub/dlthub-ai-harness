---
name: build-notebook
argument-hint: "[spec-path]"
description: This skill should be used when the user asks to "build the notebook", "launch the dashboard", "generate the marimo notebook", or when an analysis_plan.md artifact exists and the user wants to assemble or regenerate the dashboard. Reads chart specs with ibis queries and altair code from analysis_plan.md, assembles a marimo Python file, validates, and launches. Do NOT use for exploring data or planning charts (use explore-data), building pipelines (use rest-api-pipeline toolkit), or deploying (use dlthub-runtime toolkit).
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

Generate `<pipeline_name>_dashboard.py`. Read `references/notebook-patterns.md` for the complete notebook structure, cell templates, and naming conventions before generating.

## Marimo patterns

Check your context for a skill matching "Write a marimo notebook in a Python file in the right format". If found, **read it as a reference** for cell structure and reactivity patterns — do not invoke it as an action skill. If not found, use the templates in `references/notebook-patterns.md` and suggest to the user:

> **Tip:** For better marimo notebooks, install the official marimo skill: `npx skills add marimo-team/skills/marimo-notebook`

## Step 3: Validate

Run marimo's linter to catch common mistakes:

```bash
uvx marimo check <pipeline_name>_dashboard.py
```

If validation fails:
1. Read the error output — marimo check reports specific issues (missing returns, variable conflicts, import errors).
2. Fix the reported issues in the notebook file.
3. Re-run `uvx marimo check` until it passes.

## Step 4: Launch

After validation passes, offer to launch in browser or skip.

If yes:
```bash
uv run marimo edit <pipeline_name>_dashboard.py --no-token
```

Tell the user the notebook is running (default: localhost:2718).

## Regeneration

When re-invoked after iteration (see `workflow.md`): re-read the full analysis_plan.md and regenerate the entire notebook file, then validate and relaunch.

## Troubleshooting

### marimo check fails with variable conflicts
Two cells export the same variable name. Fix: follow the naming conventions in `references/notebook-patterns.md`.

### marimo check fails with import errors
A dependency is missing from the PEP 723 header. Add it to the `dependencies` list and re-check.

### Notebook runs but charts are empty
The SQL query returns no rows. Common causes:
1. Filter is too restrictive — check `where` clauses.
2. Column names don't match schema — verify against `get_table_schema`.
3. Table is empty — check `row_counts`.

### dlt.attach fails in notebook
Pipeline name is wrong or pipeline hasn't been run. Run `dlt pipeline <name> info` to verify.

## Example

**Input:** `2026-03-10_orders_pipeline_analysis_plan.md` with 2 charts (Monthly Revenue Trend + Revenue by Category)

**Output:** `orders_pipeline_dashboard.py` with 2 data cells + 2 chart cells, structured per `references/notebook-patterns.md`.

**Validation:** `uvx marimo check orders_pipeline_dashboard.py` → passes
**Launch:** `uv run marimo edit orders_pipeline_dashboard.py --no-token`

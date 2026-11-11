---
name: build-notebook
argument-hint: "[spec-path]"
description: This skill should be used when the user asks to "build the notebook", "launch the dashboard", "generate the marimo notebook", or when an analysis_plan.md artifact exists and the user wants to assemble or regenerate the dashboard. Reads chart specs with ibis queries and altair code from analysis_plan.md, assembles a marimo Python file, validates, and launches. Do NOT use for exploring data or planning charts (use explore-data), building pipelines (use rest-api-pipeline toolkit), or deploying (use dlthub-platform toolkit).
---

# Build notebook from spec

## Prerequisites
Skip this if you already checked it in this session.
1. Run `uv --version`. If it fails, `uv` is missing.
   - Ask the user to allow the `uv` install. Do not install it without approval.
   - On macOS and Linux, run `curl -LsSf https://astral.sh/uv/install.sh | sh`.
   - On Windows, run `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.
   - Docs: https://docs.astral.sh/uv/getting-started/installation/
   - If `uv` is still not found, tell the user to open a new shell, because the install changes `PATH`.
2. Run `uv run dlthub ai status`. If it fails, `dlt[hub]` or the dlthub workspace is missing.
3. Check that these skills are available. If a skill is not available, its toolkit is missing.
   - `setup-secrets` from the `init` toolkit
   - `setup-runtime` from the `dlthub-platform` toolkit
   - Do not check the `dlt-workspace-mcp` tools. They do not start without `dlt[hub]`.
4. Find how this skill was installed. Look at the folder of this skill.
   - The folder is in the project (`.claude/`, `.cursor/` or `.agents/`): the `dlthub` CLI installed it.
   - The folder is not in the project: a plugin marketplace installed it.
5. If anything is missing, tell the user that this skill does not work without it.
   - Ask the user to allow each install.
   - Install from the same channel as this skill. Then each toolkit has only one copy.
6. The `dlthub` CLI installed this skill:
   - If `dlt[hub]` or `init` is missing, run `uvx dlthub-init@latest`. It installs both.
   - For each other missing toolkit, run `uv run dlthub --non-interactive ai toolkit install <toolkit>`.
7. A plugin marketplace installed this skill:
   - If `dlt[hub]` or the workspace is missing, run `uvx --from "dlt[hub]" dlthub init`.
   - Do not run `uvx dlthub-init@latest`. It adds a second copy of `init`.
   - Ask the user to install each missing toolkit from the same marketplace.
   - In Claude Code, the command is `/plugin install <toolkit>@dlthub-ai-harness`.
8. After the install, tell the user to restart the session. Skills, rules and MCP load only at session start.
9. If the user refuses an install, stop. Do not run other steps of this skill.

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

Generate `<pipeline_name>_dashboard.py`. Read `references/notebook-patterns.md` for the complete notebook structure, cell templates, and naming conventions before generating. Every chart cell must end with `_chart` on a bare line, then `return` — without the bare expression line, nothing renders.

## Marimo patterns

For general marimo cell structure, reactivity, and best practices, fetch https://github.com/marimo-team/skills/blob/main/skills/marimo-notebook/SKILL.md. For SQL-specific patterns in marimo, fetch https://github.com/marimo-team/skills/blob/main/skills/marimo-notebook/references/SQL.md. For dlt-dashboard-specific templates, see `references/notebook-patterns.md`.

## Step 3: Validate

Run marimo's linter to catch common mistakes:

```bash
uvx marimo check <pipeline_name>_dashboard.py
```

If validation fails:
1. Read the error output — marimo check reports specific issues (missing returns, variable conflicts, import errors).
2. Fix the reported issues in the notebook file.
3. Re-run `uvx marimo check` until it passes.

## Step 4: Ensure dependencies

The notebook requires `pandas`, `numpy`, and `altair` which are **not** installed by `dlt[hub]`. In a dlthub workspace (`dlthub init`) they are already declared in `pyproject.toml` — running `uv sync` installs them.

Before launching, check if they are available. If any are missing, **ask the user** how they want to install them:

- If they are declared in `pyproject.toml` (workspace scaffolded by `dlthub init`): run `uv sync`.
- Otherwise: run `uv add pandas numpy altair` to add them to `pyproject.toml`.

Also add `marimo` if not already installed, and `ibis-framework[duckdb]` if any chart uses ibis.

**Do NOT install packages without user confirmation.**

## Step 5: Launch

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
A dependency is missing from the environment. Install it with `uv add <package>` and re-check.

### Notebook runs but charts are empty
The SQL query returns no rows. Common causes:
1. Filter is too restrictive — check `where` clauses.
2. Column names don't match schema — verify against `get_table_schema`.
3. Table is empty — check `get_row_counts` (MCP).

### dlt.attach fails in notebook
Pipeline name is wrong or pipeline hasn't been run. Run `dlthub local pipeline info <name>` to verify.

## Example

**Input:** `2026-03-10_orders_pipeline_analysis_plan.md` with 2 charts (Monthly Revenue Trend + Revenue by Category)

**Output:** `orders_pipeline_dashboard.py` with 2 data cells + 2 chart cells, structured per `references/notebook-patterns.md`.

**Validation:** `uvx marimo check orders_pipeline_dashboard.py` → passes
**Launch:** `uv run marimo edit orders_pipeline_dashboard.py --no-token`

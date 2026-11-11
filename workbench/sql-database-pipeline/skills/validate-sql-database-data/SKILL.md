---
name: validate-sql-database-data
description: Validate schema and data after a successful dlt SQL database pipeline load. Use when the user wants to check if loaded data looks correct, inspect table schemas, fix data types, or verify column mappings from the source database.
argument-hint: "[pipeline-name] [concerns]"
---

# Validate loaded data

## Prerequisites
Skip this if you already checked it in this session.
1. Run `uv --version`. If it fails, `uv` is missing.
   - Ask the user to allow the `uv` install. Do not install it without approval.
   - On macOS and Linux, run `curl -LsSf https://astral.sh/uv/install.sh | sh`.
   - On Windows, run `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.
   - Docs: https://docs.astral.sh/uv/getting-started/installation/
   - If `uv` is still not found, tell the user to open a new shell, because the install changes `PATH`.
   - If the user refuses, stop. Do not run other steps of this skill.
2. Run `uv run dlthub ai status`. It fails if `dlt[hub]` is missing.
3. Check that the `setup-secrets` skill and the `dlt-workspace-mcp` tools are available. If not, `init` is missing.
4. If anything is missing, tell the user that this skill does not work without `dlt[hub]` and `init`.
5. Ask the user to allow `uvx dlthub-init@latest`. It installs both in place.
   - On agents other than Claude Code, Cursor and Codex, ask the user to install the `init` plugin from the marketplace they used.
6. After the install, tell the user to restart the session, because rules and MCP load only at session start.
7. If the user refuses, stop. Do not run other steps of this skill.

After a successful pipeline load, verify the schema and data make sense.

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline name. If omitted, infer from session context. If ambiguous, ask the user and stop.
- `hints` (optional, after `--`): specific validation concerns (e.g. "decimal precision", "missing columns")

## 1. Inspect schema

### Export schema as mermaid

```
uv run dlthub local pipeline schema <pipeline_name> --format mermaid
```

Show the mermaid diagram to the user. This gives a quick overview of tables, columns, types, and relationships.

## 2. View the data

### For the human: Workspace Dashboard

Tell the user to run the Workspace Dashboard:
```
uv run dlthub local pipeline show <pipeline_name>
```
This opens a browser with table schemas, row counts, and sample data.

### For the agent: query via pipeline dataset API

```python
import dlt

pipeline = dlt.attach("<pipeline_name>")
dataset = pipeline.dataset()

# Row counts for all tables
dataset.row_counts().df()

# Sample rows from a table
dataset["<table_name>"].head().df()
```

Never import the destination library (e.g. `duckdb`) directly — use `pipeline.dataset()` instead, which is destination-agnostic.

## 3. Review with user

Ask the user if the schema and data look right. Common issues for SQL sources:

### Data type mismatches

The default `sqlalchemy` backend reflects types from the source DB. If types look wrong after switching backends (e.g. to `pyarrow`), check `reflection_level`:

```python
sql_table(
    table="<table>",
    reflection_level="full_with_precision",  # preserves decimal scale and string length
)
```

**IMPORTANT:** Never convert monetary or precision-sensitive values to `float`. Always keep them as `Decimal`.

### Missing or null columns

Columns that are all-null on first load won't have inferred types. Add explicit column hints:

```python
sql_table(
    table="<table>",
    columns={"amount": {"data_type": "decimal", "precision": 18, "scale": 4}},
)
```

> **Note:** `columns={}` hints do not work with backends that skip dlt normalisation (`pyarrow`, `pandas`, `connectorx`). If you need schema hints and are using one of those backends, use `table_adapter_callback` instead.

### Unexpected column names

dlt normalizes column names to snake_case by default. If source DB column names contain spaces or special chars, they are renamed. Check the schema mermaid output to see the mapped names.

## 4. Iterate

Re-run the pipeline after changes (`dev_mode=True` gives a fresh dataset each time). Use `debug-sql-database-pipeline` to inspect traces after each run. Repeat until the user is satisfied with the schema.

## Next steps

- **User is happy with the data** → use `adjust-table` to remove limits and configure incremental loading for production
- **Need to add more tables** → use `add-table`
- **Need to fix pipeline code** → edit and re-run with `debug-sql-database-pipeline`
- **User wants to explore data** → hand over to **data-exploration** toolkit for notebooks and charts

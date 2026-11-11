---
name: adjust-table
description: Adjust a working dlt SQL database pipeline for production — remove dev limits, add incremental loading, configure merge keys. Use when the user wants to remove .add_limit(), load the full table, or set up incremental loading on a cursor column. For speed/memory tuning (backend, chunk size, parallelism) use optimize-sql-performance instead. For inspecting loaded data or fixing column types/schema after a load, use validate-sql-database-data instead.
argument-hint: "[pipeline-name] [adjustments]"
---

# Adjust table loading for production

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

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline name. If omitted, infer from session context. If ambiguous, ask the user and stop.
- `hints` (optional, after `--`): specific adjustments (e.g. "add incremental on updated_at", "remove limit")

## Critical rule: verify the table before removing `.add_limit()`

`.add_limit(1)` during development loads one chunk only — a broken setup (wrong column types, large blobs) won't surface until you load the full table. Before removing it:

1. Run `validate-sql-database-data` to confirm the schema and sample data look correct.
2. Check the table's row count so you know what to expect.
3. For large tables (>1M rows), consider adding incremental loading first.

## Remove dev settings

Once the test run is validated, remove the development flags:

```python
pipeline = dlt.pipeline(
    pipeline_name="<name>",
    destination="<destination>",
    dataset_name="<name>",
    # dev_mode=True,    # remove — write to the fixed dataset name
    # progress="log",  # remove — or keep if the user wants it
)

load_info = pipeline.run(table, write_disposition="replace")  # remove .add_limit(1)
```

## Add incremental loading

Incremental loading fetches only new or updated rows on each run using a cursor column.

**Ref:** https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/configuration#incremental-loading

```python
import dlt
from dlt.sources.sql_database import sql_table

table = sql_table(
    table="<table_name>",
    incremental=dlt.sources.incremental(
        "<cursor_column>",                    # e.g. "updated_at" or "id"
        initial_value="2020-01-01T00:00:00Z", # where to start on the first run
    ),
)

pipeline.run(table, write_disposition="merge", primary_key="<pk_column>")
```

Key decisions:
- **Cursor column**: prefer `updated_at` / `modified_at` for change tracking; `id` for append-only tables
- **`write_disposition="merge"`**: required with incremental — replaces rows with matching primary key
- **`primary_key`**: set this to the table's primary key so upserts work correctly
- **`initial_value`**: where to start on the very first run — older values are excluded
- **`lag`** (Optional): re-load a trailing window each run so late-arriving or back-dated updates are caught. **The unit is inferred from the shape of the cursor value, not from your config** — dlt sniffs it with `detect_datetime_format`: a date (`"2026-08-27"`) gets **days**, a datetime (`"2026-08-27T00:00:00Z"`) gets **seconds**. So "re-load the last 7 days" is `lag=7` on a date cursor but `lag=604800` on a datetime cursor. Needs `merge` + `primary_key`, or the re-fetched rows duplicate. Ref: https://dlthub.com/docs/general-usage/incremental/lag

Check stored cursor state between runs:
```
uv run dlthub local pipeline info <pipeline_name> -v
```
Look for `last_value` in the resource state.

Ref: https://dlthub.com/docs/general-usage/incremental/troubleshooting.md

## Run the first full load

```
uv run python <name>_pipeline.py
```

Use `debug-sql-database-pipeline` to inspect the first full run — large tables can surface new issues (timeouts, type errors on edge-case values, memory pressure).

## Next steps

- **Full load complete** → hand over to **data-exploration** toolkit or **dlthub-platform** to deploy
- **Slow or memory-heavy load** → use `optimize-sql-performance` (backend, chunk size, parallel tables, push-down)
- **Errors on full load** → use `debug-sql-database-pipeline`
- **Need more tables** → use `add-table`

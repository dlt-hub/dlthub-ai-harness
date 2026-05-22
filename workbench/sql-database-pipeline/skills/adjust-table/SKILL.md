---
name: adjust-table
description: Adjust a working dlt SQL database pipeline for production — remove dev limits, add incremental loading, configure merge keys. Use when the user wants to remove .add_limit(), load the full table, or set up incremental loading on a cursor column.
argument-hint: "[pipeline-name] [adjustments]"
---

# Adjust table loading for production

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline name. If omitted, infer from session context. If ambiguous, ask the user and stop.
- `hints` (optional, after `--`): specific adjustments (e.g. "add incremental on updated_at", "remove limit")

## Critical rule: verify the table before removing `.add_limit()`

`.add_limit(1)` during development loads one chunk only — a broken setup (wrong column types, large blobs) won't surface until you load the full table. Before removing it:

1. Run `validate-data` to confirm the schema and sample data look correct.
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

**Ref:** https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/basic#incremental-loading

```python
import dlt
from dlt.sources.sql_database import sql_table

table = sql_table(
    table="<table_name>",
    incremental=dlt.sources.incremental(
        "<cursor_column>",                    # e.g. "updated_at" or "id"
        initial_value="2020-01-01T00:00:00Z", # where to start on the first run
    ),
    chunk_size=500,
    backend="pyarrow",
)

pipeline.run(table, write_disposition="merge", primary_key="<pk_column>")
```

Key decisions:
- **Cursor column**: prefer `updated_at` / `modified_at` for change tracking; `id` for append-only tables
- **`write_disposition="merge"`**: required with incremental — replaces rows with matching primary key
- **`primary_key`**: set this to the table's primary key so upserts work correctly
- **`initial_value`**: where to start on the very first run — older values are excluded

Check stored cursor state between runs:
```
dlt pipeline -v <pipeline_name> info
```
Look for `last_value` in the resource state.

Ref: https://dlthub.com/docs/general-usage/incremental/troubleshooting.md

## Run the first full load

```
uv run python <name>_pipeline.py
```

Use `debug-pipeline` to inspect the first full run — large tables can surface new issues (timeouts, type errors on edge-case values, memory pressure).

## Next steps

- **Full load complete** → hand over to **data-exploration** toolkit or **dlthub-platform** to deploy
- **Errors on full load** → use `debug-pipeline`; consider reducing `chunk_size` or switching backend
- **Need more tables** → use `add-table`

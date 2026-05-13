---
name: debug-pipeline
description: Debug and inspect a dlt SQL database pipeline after running it. Use after a pipeline run (success or failure) to inspect traces, load packages, schema, and diagnose errors like connection failures, missing credentials, driver issues, or failed jobs.
argument-hint: "[pipeline-name] [issue]"
---

# Debug a SQL database dlt pipeline

**Essential Reading:** 
- https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/troubleshooting
- https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/advanced

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline name. If omitted, infer from session context. If ambiguous, ask the user and stop.
- `hints` (optional, after `--`): specific issue to investigate

## Before debugging: increase verbosity

Always do this first before any pipeline debugging:

**IMPORTANT:** Note the current values before changing them so you can restore exactly what you changed — only revert what YOU modified.

1. **Set log level to INFO** in `.dlt/config.toml`:
   ```toml
   [runtime]
   log_level = "INFO"
   ```

2. **Add progress logging** to the `dlt.pipeline()` call:
   ```python
   pipeline = dlt.pipeline(..., progress="log")
   ```
   NOTE: `progress` goes on `dlt.pipeline()`, **not** on `pipeline.run()` — that argument does not exist on `run()`.

This shows SQL queries being executed, rows fetched, reflection steps, and normalize/load progress.

## Run the pipeline

```
uv run python <source>_pipeline.py
```

### Common exceptions and what they mean

| Exception | Cause |
|---|---|
| `ConfigFieldMissingException` | A credentials field is missing or misnamed in `secrets.toml` — check the section name and field names exactly |
| `OperationalError` / `Can't connect` | Wrong host, port, or credentials; DB not reachable from this network |
| `ModuleNotFoundError: No module named 'sqlalchemy'` | Run `uv add "dlt[sql_database]"` |
| `ModuleNotFoundError: No module named 'pymysql'` | Install the dialect driver, e.g. `uv add pymysql` |
| `MissingDependencyException: numpy required` | The pyarrow backend also needs numpy: `uv add numpy` |
| `NoSuchTableError` | Table name or schema is wrong — check spelling and schema parameter |
| `PipelineStepFailed` at extract | Check the full traceback; usually a connection or reflection error |

### Pipeline loads 0 rows

- Check that the table name matches exactly (case-sensitive on some databases)
- If using `schema=`, verify the schema name is correct
- Run `DESCRIBE <table>` or `SELECT COUNT(*) FROM <table>` directly against the DB to confirm data exists

### Pipeline appears stuck / runs too long

Large tables with no `add_limit()` can take a long time — check `progress="log"` output to confirm rows are flowing. If truly stuck:

- The DB may be throttling or has a slow full-scan — add a `WHERE` clause via `query_adapter_callback`
- Try `chunk_size=100` to reduce memory pressure and confirm rows are trickling through
- To isolate which table is slow in a multi-table pipeline, load one table at a time:
  ```python
  source = sql_database(table_names=["orders", "users"])
  pipeline.run(source.with_resources("orders").add_limit(1))
  ```

**Check that `table_names` is set on the source, not filtered via `.with_resources()`.**

`sql_database()` without `table_names` reflects the entire schema before filtering — slow on large databases. Always pass the tables you need upfront:

```python
# good — reflects only these two tables
source = sql_database(table_names=["family", "clan"])

# slow — reflects all tables in the schema first, then filters
source = sql_database().with_resources("family", "clan")
```

**Check the backend — this is the most common cause of slow pipelines.**

The default `sqlalchemy` backend fetches rows one at a time through Python objects. Switch to a faster backend:

| Backend | Speed | Notes |
| --- | --- | --- |
| `sqlalchemy` | baseline | Default; safe but slow |
| `pyarrow` | ~20–30x faster | Best general upgrade; also needs `numpy` (`uv add numpy`) |
| `connectorx` | ~2x faster than pyarrow | Rust-based; great for large MySQL/PostgreSQL tables; uses its own connection string format |

Apply by passing `backend=` to `sql_table` or `sql_database`:
```python
source = sql_database(table_names=["orders"], backend="pyarrow")
# or
source = sql_database(table_names=["orders"], backend="connectorx")
```

Ref: https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/configuration#configuring-the-backend

### Incremental loading stops picking up new data

Inspect pipeline state to check the stored cursor value:
```
dlt pipeline -v <pipeline_name> info
```
Look for `last_value` in the resource state — verify it updates between runs. Also check logs for `"Bind incremental on <resource_name>"` to confirm the incremental param was bound.
Ref: https://dlthub.com/docs/general-usage/incremental/troubleshooting.md


## Post-mortem debugging

Inspect the last pipeline run:

```
dlt pipeline -vv <pipeline_name> trace
```

`-vv` goes BEFORE the pipeline name. Shows credentials resolution, step timing, and failures.

## Load packages
Each pipeline run generated one or more load packages. Use trace tool to find their ids.

```
dlt pipeline -v <pipeline_name> load-package          # most recent package
dlt pipeline -v <pipeline_name> load-package <load_id> # specific package
```
Shows package state, per-job details (table, file type, size, timing), and **error messages for failed jobs**. With `-v` also shows schema updates applied.

```
dlt pipeline <pipeline_name> failed-jobs
```
Scans all packages for failed jobs and displays error messages from the destination.

### Inspecting raw load files

Load packages are stored at `~/.dlt/pipelines/<pipeline_name>/load/loaded/<load_id>/`. Job files live in `completed_jobs/` and `failed_jobs/` subdirectories.

File format depends on the destination:

| Format | Default for | File extension |
|---|---|---|
| INSERT VALUES | duckdb, postgres, redshift, mssql, motherduck | `.insert_values.gz` |
| JSONL | bigquery, snowflake, filesystem | `.jsonl.gz` |
| Parquet | athena, databricks (also supported by duckdb, bigquery, snowflake) | `.parquet` |
| CSV | filesystem | `.csv.gz` |

Inspect gzipped files with `zcat`:
```
zcat ~/.dlt/pipelines/<pipeline_name>/load/loaded/<load_id>/completed_jobs/<file>.gz
```
Useful for verifying data transformations and debugging destination errors.

## Clean up after debugging

Before moving on, revert all debugging settings YOU introduced:

- [ ] `.dlt/config.toml` — restore `log_level` to its previous value (or remove if you added it)
- [ ] Pipeline script — remove `progress="log"` from `dlt.pipeline()` if you added it. Remove `.add_limit(N)` if you added it for debugging.

Do NOT remove settings the user had before you started.

## Next steps

- **Load successful** → use `validate-data` to inspect schema and data, or hand over to `explore-data` (`data-exploration` toolkit) to jump straight into charts and analysis
- **Config/secrets missing** → revisit `create-sql-database-pipeline` — "Set up config and secrets" section
- **No pipeline exists yet** → use `create-sql-database-pipeline` to scaffold one first

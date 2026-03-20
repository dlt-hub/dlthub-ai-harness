---
name: debug-pipeline
description: Debug and inspect a dlt pipeline after running it. Use after a pipeline run (success or failure) to inspect traces, load packages, schema, data, and diagnose errors like missing credentials or failed jobs.
argument-hint: "[pipeline-name] [issue]"
---

# Debug a dlt pipeline

**Essential Reading** https://dlthub.com/docs/reference/explainers/how-dlt-works

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline name. If omitted, infer from session context. If ambiguous, ask the user and stop.
- `hints` (optional, after `--`): specific issue to investigate

## Before debugging: increase verbosity

Always do this first before any pipeline debugging:

**IMPORTANT:** Before making changes, note the current values in config files and pipeline code so you can restore them exactly. You are changing the user's files — only revert what YOU changed.

1. **Set log level to INFO** in `.dlt/config.toml`:
   ```toml
   [runtime]
   log_level="INFO"
   ```

2. **Show HTTP error response bodies** (hidden by default!):
   ```toml
   [runtime]
   http_show_error_body = true
   ```

3. **Add progress logging** to the `dlt.pipeline()` call (NOT `pipeline.run()` — that argument doesn't exist):
   ```python
   pipeline = dlt.pipeline(..., progress="log")
   ```

This shows HTTP requests being made, data extracted, pagination steps, and normalize/load progress. Essential for diagnosing any issue.
**Essential reading if problems PERSIST**: https://dlthub.com/docs/general-usage/http/rest-client.md

## Run the pipeline

```
uv run python <source>_pipeline.py
```

Common exceptions and what they mean:
- `ConfigFieldMissingException` - config / secrets are missing. inspect exception message
- `PipelineFailedException` - pipeline failed in one of the steps. inspect exception trace to find a root cause. find **load_id** to identify load package that failed

In extract step most of the exceptions are coming from source/resource code that you wrote!

### First run of the pipeline

**Suggest to run** the pipeline before asking the user to fill in credentials:

Expected: a `ConfigFieldMissingException` or `401 Unauthorized` error confirming:
- The pipeline structure is correct
- Config/secrets resolution is wired up properly
- The right API endpoint is being hit

Tell the user what credentials to fill in and how to get them. If credentials are unknown, research the data source (web search for API docs, auth setup guides — similar to what `find-source` does).

After any run (success or failure), use the dlt CLI for inspection:

### Pipeline appears stuck / runs too long

A pipeline that runs for a long time is suspicious but MAY be normal (large datasets). Analyze stdout before killing it:

**Paginator loops forever** — repeated requests to the same URL or page:
- dlt's auto-detected paginator can guess wrong and loop. Fix: set an explicit `"paginator"` in the resource config.
- `OffsetPaginator`/`PageNumberPaginator` without `stop_after_empty_page=True` require `total_path` or `maximum_offset`/`maximum_page`, otherwise they loop forever.
- `JSONResponseCursorPaginator` with wrong `cursor_path` → cursor never advances → infinite loop.

**Silent retries look like a hang** — the pipeline may be retrying failed HTTP requests:
- Default: 5 retries with exponential backoff (up to 16s per attempt), 60s request timeout.
- A single failing endpoint can stall for 60-80+ seconds before raising an error.
- Override in `.dlt/config.toml` for faster failure during debugging:
  ```toml
  [runtime]
  request_timeout = 15
  request_max_attempts = 2
  ```
- Ref: https://dlthub.com/docs/general-usage/http/requests.md (timeouts and retries)

**Working but slow** — each request returns new data and URL changes. Use `.add_limit(N)` to cap pages during development.

**Can't tell which resource is stuck** in a multi-resource pipeline — switch to sequential extraction:
```toml
[extract]
next_item_mode = "fifo"
```
This makes one resource complete fully before the next starts, making logs much easier to follow.
Ref: https://dlthub.com/docs/reference/performance.md (extraction modes)

### Pipeline succeeds but loads 0 rows

Likely a wrong or missing `data_selector`. dlt auto-detects the data array in the response but can fail silently on complex/nested responses. Fix: explicitly set `data_selector` as a JSONPath to the array (e.g. `"data"`, `"results.items"`).

### Incremental loading stops picking up new data

Inspect pipeline state to check the stored cursor value:
```
dlt pipeline -v <pipeline_name> info
```
Look for `last_value` in the resource state — verify it updates between runs. Also check logs for `"Bind incremental on <resource_name>"` to confirm the incremental param was bound.
Ref: https://dlthub.com/docs/general-usage/incremental/troubleshooting.md


## Post mortem debugging and trace
You can inspect last pipeline run:

```
dlt pipeline -vv <pipeline_name> trace
```
Note: `-vv` goes BEFORE the pipeline name. Shows config/secret resolution, step timing, failures.

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

Before moving on, revert all debugging settings YOU introduced. Only revert what you changed — preserve any user settings that existed before.

Checklist:
- [ ] `.dlt/config.toml` — restore `log_level` to its previous value (e.g. `WARNING`). Remove `http_show_error_body`, `request_timeout`, `request_max_attempts` if you added them. Remove `[extract] next_item_mode` if you added it.
- [ ] Pipeline script — remove `progress="log"` from `dlt.pipeline()` if you added it. Remove `.add_limit(N)` if you added it for debugging.

Do NOT remove settings the user had before you started debugging.

## Next steps

- **Load successful** → use `validate-data` to inspect schema and data, or hand over to `explore-data` (data-exploration toolkit) to jump straight into charts and analysis
- **Config/secrets missing** → check TOML sections, revisit `create-rest-api-pipeline` step 6b for credential setup
- **No pipeline exists** → use `create-rest-api-pipeline` to scaffold one first

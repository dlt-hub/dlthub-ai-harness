---
name: new-pipeline-health
description: "Use for a deep check of pipelines that are new in production on dltHub, or when the user asks whether a new pipeline loads what it should: row counts that jump or stay flat, a full load on every run, an incremental cursor that filters almost everything, runs that load nothing, a merge table that grows like append. Takes a pipeline name, or finds the pipelines that started producing data in the last 7 days. Reads traces, row metrics and the dataset, and runs isolated experiments against the source."
argument-hint: "[pipeline-name] [environment]"
---

# New pipeline health

A new pipeline can succeed on every run and still load the wrong data: everything again, nothing new, or a slice. Check
its traces and row metrics first, then its dataset, then the source itself.

**Reference**: `workspace-tasks-reference.md` of the (`debug-deployment`) skill: the tool and the command for each task, and the
profile each one runs with ·
https://dlthub.com/docs/general-usage/incremental/troubleshooting.md ·
https://dlthub.com/docs/general-usage/dataset-access/dataset.md

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the pipeline to check. Without it, step 1 finds the new ones.
- `environment` (optional): without it, the environment of the active profile, else `prod`.

## 0. Profiles

| What | Runs with |
|---|---|
| telemetry and job runs (`dlthub_*`) | `environment` |
| the dataset (step 4) | `access`, else `prod`, after a yes. Restore the pipeline first |
| source experiments (step 5) | the profile whose secrets hold the source credentials, after a yes. A local DuckDB destination only |

- `uv run dlthub ai secrets view-redacted` shows which profile holds the source keys: names, never values.
- Nothing is written to the production destination. When you are done, `dev` is the active profile again.

## 1. Find the pipelines

- A pipeline name given: check that one.
- Otherwise, run `dlthub_get_telemetry_status` first, because stale telemetry hides runs.
- Then compare `dlthub_list_pipelines {"days": 7}` with `{"days": 365}`. A pipeline with the same run count and the
  same `total_rows_loaded` in both windows started producing data in the last 7 days.
- More than three found: list them and ask which to check.

## 2. Traces and row metrics

For each pipeline:

1. `dlthub_list_pipeline_runs {"pipeline_name": "<name>", "days": 7}`: status, rows and duration of each run.
2. `dlthub_get_pipeline_run` for a few runs: rows and write disposition per table, and the load packages.
3. `dlthub_get_pipeline_run_trace {"pipeline_run_id": "<id>", "detail": "full", "step": "extract"}`: the metrics of
   each resource, with the incremental rows of step 3.

Anomalies:
- every run loads about the same number of rows: a full load each time (step 3);
- rows jump or drop by an order of magnitude between runs;
- runs that succeed with 0 rows (`dlthub_list_pipeline_runs {"empty_only": true}`);
- a `merge` table that grows on every run like `append`: the primary key is missing or not unique;
- a child table that grows while its parent does not;
- many more items extracted than rows loaded: a schema contract or a filter drops them.

## 3. The incremental check

`dlt.sources.incremental` counts what it filters. In the extract step's metrics, a resource with an incremental
carries `incremental` rows next to its own `items_count`:

| Metric | What it counts |
|---|---|
| `unfiltered_items_count` | items the resource yielded, before the cursor filter |
| `items_count` of the resource | items left after the filter |
| `final_unique_hashes_count` | rows on the cursor's last value, kept to deduplicate the next run |

- **Most items filtered on every run**, for example 48,000 unfiltered and 150 kept: the source returns everything and
  the cursor filters it on this side. Every run extracts the full data. Pass `incremental.last_value` to the source
  (the API parameter or the `WHERE` of the query), so it returns only new items.
- **Nothing filtered and the same rows every run**: the cursor does not advance. See "Incremental loading stops
  picking up new data" in (`troubleshoot-pipeline-run`).
- **`final_unique_hashes_count` in the thousands**: many rows share the last cursor value, and every run reads them
  again. A finer cursor helps, for example a timestamp instead of a date.

## 4. Row counts by load id

**Ask** for access to production data first. Then restore the pipeline into the profile, as "Access production data"
in the (`debug-deployment`) skill says, and read with the dataset interface:

```py
# WORKSPACE__PROFILE=access uv run python row_counts.py
import dlt

dataset = dlt.attach("github_issues").dataset()
for load_id in dataset.load_ids()[-5:]:                       # the last five loads, oldest first
    print(load_id, dataset.row_counts(load_id=load_id).df().to_dict("records"))
print(dataset.row_counts().df())                              # all rows per table
print(dataset.query("SELECT COUNT(*), COUNT(DISTINCT id) FROM issues").fetchall())
```

- Compare the rows of each load id with the telemetry rows of the same run.
- In a `merge` table, compare the rows with the distinct primary keys: more rows than keys means duplicates.
- Rows that only grow on a `replace` table, or a load id without rows in a table that should get them, go in the
  report with the load id.

## 5. Isolated experiments with the source

Only after the user allows reading the source with its credentials. Name the profile whose secrets hold them. Load
into a throwaway local pipeline, never into the production destination:

```py
# WORKSPACE__PROFILE=prod uv run python experiment.py
import dlt
from github_pipeline import github_source  # the source the job runs

source = github_source().with_resources("issues").add_limit(2)
pipeline = dlt.pipeline("exp_issues", destination="duckdb", dev_mode=True)
pipeline.run(source)
print(pipeline.last_trace.last_extract_info.metrics)
```

- Set the cursor's `initial_value` near today: does the source return only recent items, or everything?
- Run twice: does the second run extract fewer items?
- Print a few records to see the real field names of the cursor and the primary key.
- Afterwards, delete the script and the experiment's folders under `.dlt/state/<profile>/pipelines/exp_issues/` and
  `.dlt/data/<profile>/`.

## 6. Report

Per pipeline, a verdict, the anomalies with their evidence (the run id or the load id, and the numbers) and the fix in
the pipeline code:

```
github_issues (new since 2026-11-17, 7 runs)
- full extract on every run: issues yields ~48,000 items, 150 kept (trace of pipeline run 3f2a…, extract step)
  -> pass the cursor to the API: since=<last_value> on the issues endpoint
- merge table issues grows like append: 48,000 then 96,000 rows in two loads (row_counts by load id)
  -> set primary_key="id" on the issues resource
```

A fix goes through (`define-and-debug-jobs`), then (`deploy-workspace`).

---
name: daily-workspace-health
description: "Use for the daily check of a workspace deployed on dltHub, or when the user asks for the status of the workspace, production or the deployment: are my pipelines running, is the data coming, what happened overnight, what's up with job or pipeline X. Inspects failed job runs, checks that pipelines ran on time and the data is fresh, and investigates a problem in the dataset. Not for a deep look at a new pipeline (new-pipeline-health)."
argument-hint: "[job-or-pipeline] [environment]"
---

# Daily workspace health

The morning check: what ran since yesterday, what failed, what is late, and whether the data arrived. This skill reads
and reports. Every action waits for the user.

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/monitoring.md · `workspace-tasks-reference.md` of the
(`debug-deployment`) skill: the tool and the command for each task, and the profile each one runs with

Parse `$ARGUMENTS`:
- `job-or-pipeline` (optional): check this job or pipeline only.
- `environment` (optional): the environment to check. Without it, the environment of the active profile, else `prod`.

## 0. Profiles

- The `dlthub_*` tools and `dlthub job …` commands read an **environment**. Pass `environment` on every call when it
  is not the default one.
- Reading data (step 5) needs a **profile**: `access`, else `prod`. **ALWAYS** ask the user first.
- When you are done, `dev` is the active profile again.

## 1. Failed job runs first

1. `dlthub_get_workspace`: the remote workspace and its dashboard URL.
2. `dlthub_list_job_runs {"limit": 20}`, newest first. It has no time filter: page with `offset` until the runs are
   older than 24 hours.
3. Note each failed, cancelled and still-running run. The rows carry the pipelines and row counts of each run, so do
   not call `dlthub_get_job_run` per row.
4. A failed run may already have an agent's diagnosis: a run of an agent job whose `previous_job_run_id` is the failed
   run. Read it with `dlthub_get_job_run_result`, and report it as the agent's claim.

One job or pipeline named: `dlthub_list_job_runs {"job_ref": "<job ref>"}`, or
`dlthub_list_pipelines {"pipeline_name": "<name>", "days": 7}`, and steps 2 and 3 for it only.

## 2. Did the pipelines run on time

1. `dlthub_get_telemetry_status` first. When telemetry is stale or never reported, say so in the report: every zero
   below then means "unknown", not "nothing ran". A stale watermark looks exactly like a quiet week.
2. `dlthub_list_jobs`, against the runs of step 1: a scheduled job without a run in its window went quiet.
   `dlthub_get_job` gives its triggers, its next scheduled run and whether it is paused.
3. `dlthub_list_pipelines {"days": 1}`: `latest_pipeline_run_at` and `latest_status` of each pipeline, against the
   schedule of its job.

## 3. Is the data fresh

1. `total_rows_loaded` of `dlthub_list_pipelines {"days": 1}`, against `{"days": 7}`:
   - a pipeline far below its daily average;
   - `success_ratio` under 1 for the week: a flaky pipeline. It "fails a third of the time", not "failed once".
2. `dlthub_list_pipeline_runs {"days": 1, "empty_only": true}`: runs that succeeded and loaded nothing. A silent
   no-op looks like this.
3. `dlthub_list_datasets`: a dataset written by more than one pipeline is shared. A table that looks wrong may come
   from another pipeline than the one you check.

## 4. Report, then ask

```
Workspace acme-analytics, environment prod (dashboard: https://…)
Telemetry: last record 12 min ago
Last 24 h: 26 job runs, 23 completed, 2 failed, 1 running

- failed: jobs.github.load_issues #812 at 06:05, ConfigFieldMissingException (log line 41) -> debug it?
- late: jobs.reports.daily, scheduled 06:00, last run 2026-11-20, paused -> resume it?
- empty: pipeline stripe_events loaded 0 rows in its last 3 runs -> check its incremental cursor?
- flaky: pipeline github_issues, 5 of 7 runs succeeded this week
```

- Quote an error as the log or the trace states it, with the run number. "It failed" says nothing.
- **Ask** which item to look into. Nothing is re-run, resumed or fixed without a yes.

## 5. Investigate the dataset

Only for a problem with the data, and after the user agrees to read production data:

1. Restore the pipeline into the profile, as "Access production data" in the (`debug-deployment`) skill says. The
   local state of a pipeline that runs on the platform is stale.
2. Read with the dataset interface, on that profile:

   ```py
   # WORKSPACE__PROFILE=access uv run python check_freshness.py
   import dlt

   dataset = dlt.attach("github_issues").dataset()
   print(dataset.loads_table().df().tail(5))                       # when the last loads finished
   print(dataset.row_counts(load_id=dataset.latest_load_id()).df())  # rows per table in the last load
   print(dataset.query("SELECT MAX(updated_at) FROM issues").fetchall())  # the newest record
   ```

3. Compare the last load with the schedule, its rows with the telemetry, and the newest record with today.

## Troubleshooting

| What you see | Check | Next |
|---|---|---|
| a failed job run | its log and the trace of its pipeline run | (`debug-deployment`) |
| zeros everywhere | `dlthub_get_telemetry_status` | stale telemetry: report it, not the zeros |
| a job without a run in its window | `dlthub_get_job`: paused, triggers, next run | a pause is the operator's decision: ask before `dlthub job resume` |
| a pipeline is late | the runs of its job, and of the job that produces its input | (`debug-deployment`) for the producer |
| 0 rows loaded | `empty_only` runs, the extract step of the trace | an incremental cursor or a filter: (`new-pipeline-health`), step 3 |
| flaky | the traces of the failed runs | the same error every time is not transient: (`debug-deployment`) |
| stale or wrong rows in a table | `dlthub_list_datasets`: does another pipeline write it? | step 5 |
| a run fails on a credential | `dlthub_list_variables`: a name missing in the scope of the run | (`setup-secrets`) |
| a job names a profile that is not defined | `dlthub_get_configuration_files` | (`setup-profiles`) |
| a run is still going | no stored log yet | `dlthub job logs <name> -f` |

## Next

- A failed run → (`debug-deployment`).
- A new pipeline, or one that loads oddly → (`new-pipeline-health`).
- A code or config fix → (`define-and-debug-jobs`), then (`deploy-workspace`).

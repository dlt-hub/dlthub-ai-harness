---
name: maintain-snowflake-jobs
description: "Use when a job on Snowflake failed or is slow, the user asks about job runs, logs, schedules or Snowflake tasks of the workspace, or wants to pause, resume, cancel or start a job. Inspects and controls the deployed jobs. Not for changing what a job does: fix the code, then deploy-snowflake-workspace."
argument-hint: "[job-or-run-id] [environment]"
---

# Daily maintenance of jobs on Snowflake

Each batch job is a Snowflake task. Each job run is a job service, and the dltHub app keeps the record of every job
run. The `dlthub snowflake` commands read all three, so start with them.

**Reference**: `README.md` § Daily commands · `docs/ARCHITECTURE.md` § Job runs on Snowflake tasks and § Pause,
cancel and timeouts · `uv run dlthub snowflake <command> --help`

Every command takes `--environment <name>` for another environment than `prod`. A job is its name
(for example `load_github_actions`) or the last two parts of its job ref (`<module>.<name>`, for example
`github_pipeline.load_github_actions`). The MCP tools
`snowflake_list_jobs`, `snowflake_list_job_runs` and `snowflake_get_run_logs` read the same data.

## 1. See the state

```sh
uv run dlthub snowflake job list                    # every job, its trigger, schedule on or off, latest job run
uv run dlthub snowflake job-runs list --job load_github_actions   # the latest job runs, newest first
```

Find the job run the user means. Take its **dltHub Run ID**: the other commands take it, or the job name for the
latest job run.

## 2. Read the job run and its logs

```sh
uv run dlthub snowflake job-runs info <run id>   # status, times, error, Snowflake ids and Snowsight links
uv run dlthub snowflake logs <run id>            # the logs of the job run; -f follows a running one
```

- `job-runs show <run id>` and `logs show <run id>` open Snowsight, for the user.
- The app keeps no log lines. `logs` reads the job service while it answers, then the log history of Snowflake:
  the event table of the account has every line a few minutes after the job run ends.

## 3. Find the cause

Use the status, the error and the end of the log. `docs/ARCHITECTURE.md` § Job runs on Snowflake tasks has the
table of failure cases.

| What you see | Likely cause | Next |
|---|---|---|
| a Python traceback in the job code: source, schema, load errors | the pipeline | **rest-api-pipeline** → `debug-pipeline`, then redeploy |
| SQL errors in a transformation that ran locally on DuckDB | the SQL dialect | **transformations** → `debug-transformation` |
| a connect error or "insufficient privileges" on the destination | the data connection | (`setup-snowflake-data-connection`) |
| a missing config or secret value | the secrets of the profile | `secrets list`, then (`setup-secrets`) and redeploy |
| a network error to the source host | egress | the external access integration: `egress_hosts`, or an admin |
| `failed` with no job run in the app, Snowflake task failed | the container failed before the runner started | `job-runs info`, then [snowflake-objects.md](snowflake-objects.md) |
| the job run expired, or was stopped at the timeout | the timeout | ask before you raise `execute.timeout` |
| out of memory, killed | the container size | ask before you raise `require.instance.size` |

Every error of the commands says what happened, why and what to run. Follow it first. When the CLI is not enough,
read [snowflake-objects.md](snowflake-objects.md): it has the SQL for the Snowflake tasks and job services.

## 4. Act

Show the command and get a yes before each one: they change what runs.

```sh
uv run dlthub snowflake job pause <job>       # suspends the schedule; manual job runs and follow-ups still start
uv run dlthub snowflake job resume <job>      # starts the schedule again; the first job run covers the pause
uv run dlthub snowflake job cancel <job>      # cancels every running job run of the job; it gets about 30 s
uv run dlthub snowflake job-runs cancel <run id>   # cancels one job run
uv run dlthub snowflake trigger <job>         # starts a deployed job, deploys nothing; --dry-run lists matches
```

- A selector names several jobs: `tag:<name>` (every job with the tag) or `every:*` (every scheduled job), for example
  `job pause every:*`. Run `trigger --dry-run` or `job cancel --dry-run` to see the matches first.
- A deploy keeps a paused job paused unless its schedule changed.
- After a code fix: deploy again (`deploy-snowflake-workspace`, steps 2–4), then follow one job run with
  `run <job> -f`.

## 5. Secrets

```sh
uv run dlthub snowflake secrets list          # the secrets files of the environment and the Snowflake secrets deploy pushed
uv run dlthub snowflake secrets wipe <secret> # drops one Snowflake secret after it asks; the next deploy pushes it again
```

Names only: never print a secret value. To change a value, change the secrets file with (`setup-secrets`) and
deploy again.

## 6. Report

Tell the user what happened, the cause, what you changed, and what to watch. Example: "`load_github_actions` failed
at 06:00 on a 401 from the GitHub API: the token expired. After the new token in `prod.secrets.toml` and a deploy,
the next job run completed in 3 min."

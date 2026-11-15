# The Snowflake objects of a deployment

Read this when the `dlthub snowflake` commands do not explain a failure. It is not in the docs yet. The SQL runs as
the deploying role: it owns the workspace schema, the Snowflake tasks and the job services.

## What is in the workspace schema

`<database>.DLTHUB_<REMOTE WORKSPACE>`, for example `ANALYTICS.DLTHUB_GITHUB_ACTIONS` (`uv run dlthub snowflake info`
shows it):

| Object | Name | What it does |
|---|---|---|
| Snowflake task | one per batch job, named after its job ref, for example `PIPELINES_LOAD_GITHUB_ACTIONS` | its schedule, config, overlap policy and timeout; it calls `DLTHUB_RUN_JOB` |
| procedure | `DLTHUB_RUN_JOB` | starts the job service of a job run and closes the job run in the app |
| procedure | `DLTHUB_DISPATCH` | starts the follow-up Snowflake tasks after a job run closes |
| job service | `<task name>_<uuid>`, one per job run | runs the workspace image; it is gone after the job run, its logs stay in the event table |
| secrets | one per secrets file of the environment | the job reads them with the Snowflake secrets provider |

## Snowflake tasks

```sql
SHOW TASKS IN SCHEMA ANALYTICS.DLTHUB_GITHUB_ACTIONS;

-- the task runs of the last 24 hours, with their errors
SELECT name, state, error_message, query_id, scheduled_time
FROM TABLE(ANALYTICS.INFORMATION_SCHEMA.TASK_HISTORY(
  SCHEDULED_TIME_RANGE_START => DATEADD('hour', -24, CURRENT_TIMESTAMP()),
  TASK_NAME => 'PIPELINES_LOAD_GITHUB_ACTIONS'));
```

- `state` `SUSPENDED` in `SHOW TASKS`: the job is paused. Use `job resume`, never `ALTER TASK` by hand.
- A task run that failed with no job run in the app: the container failed before the runner registered the job run.
  The `error_message` of the task run has the reason.
- `SKIPPED`: the previous job run was still running and the job allows no overlap (`execute.concurrency`).

## Job services and their logs

```sql
-- while the job service runs: the last lines of the runner container
SELECT SYSTEM$GET_SERVICE_LOGS('ANALYTICS.DLTHUB_GITHUB_ACTIONS.PIPELINES_LOAD_GITHUB_ACTIONS_<uuid>', '0', 'runner', 500);

-- after it ends: the log history of the service from the event table
SELECT TIMESTAMP, LOG
FROM TABLE(ANALYTICS.DLTHUB_GITHUB_ACTIONS.PIPELINES_LOAD_GITHUB_ACTIONS_<uuid>!SPCS_GET_LOGS())
WHERE CONTAINER_NAME = 'runner'
ORDER BY TIMESTAMP;
```

`job-runs info <run id>` prints the name of the job service. The **Job Service ID** that Snowsight shows is visible
only to the owning role, for 30 days.

The log history needs an event table on the account (`SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT`). Without one,
only the last 100 lines that the app keeps are left after the job service is gone.

## Rules

- Change Snowflake tasks only with the `dlthub snowflake` commands and deploy. A hand edit is overwritten or makes
  the task differ from the code (`job info` shows "not in sync").
- Never drop the workspace schema or its objects without the user's explicit yes: the job runs and the schedules go
  with them.

# Scheduling and Triggers

Triggers tell Runtime **when** to run a job. Declare them in the decorator --
there is no CLI command for adding or removing schedules. Change the code,
redeploy.

## Adding a schedule to an existing job

Without a trigger:
```python
@run.pipeline("my_pipeline")
def ingest_data():
    ...
```

With a trigger -- run daily at midnight UTC:
```python
from dlt.hub.run import trigger

@run.pipeline("my_pipeline", trigger=trigger.schedule("0 0 * * *"))
def ingest_data():
    ...
```

A bare cron string also works as shorthand:
```python
@run.pipeline("my_pipeline", trigger="0 0 * * *")
```

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/triggers.md (cron, intervals, follow-up chains, freshness constraints)

## Common cron patterns

Use [crontab.guru](https://crontab.guru) to build and test expressions.

## Trigger types

| Type | Constructor | Example |
|------|-------------|---------|
| `schedule` | `trigger.schedule("0 8 * * *")` | Cron expression |
| `every` | `trigger.every("6h")` | Recurring interval (`"5m"`, `"1h"`, seconds as float) |
| `once` | `trigger.once("2026-12-31T23:59:59Z")` | One-shot at a timestamp |
| `job.success` | `upstream_job.success` | Fires when upstream succeeds |
| `job.fail` | `upstream_job.fail` | Fires when upstream fails |
| `tag` | `trigger.tag("backfill")` | Broadcast -- fires every job with this tag |

## Followup triggers

Chain jobs by referencing the upstream decorated function:

```python
@run.pipeline("ingest_pipeline", trigger=trigger.schedule("0 * * * *"))
def ingest():
    ...

@run.pipeline("transform_pipeline", trigger=ingest.success)
def transform():
    ...
```

`transform` runs automatically every time `ingest` succeeds.

## Multiple triggers

Pass a list -- the job runs when **any** trigger fires:

```python
@run.pipeline(
    "my_pipeline",
    trigger=[trigger.schedule("0 8 * * *"), backfill_job.success],
)
def daily_load():
    ...
```

## After adding triggers

Deploy and verify:

```bash
dlthub deploy                    # sync manifest to Runtime
dlthub deploy --dry-run          # preview without applying
dlthub job list                  # confirm triggers are set
```

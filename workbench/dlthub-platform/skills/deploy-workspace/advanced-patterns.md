# Advanced Deployment Patterns

## Followup jobs

Chain a transform to run after ingest succeeds:

```python
@run.pipeline("ingest_pipeline", trigger=trigger.schedule("0 * * * *"))
def ingest():
    ...

@run.pipeline("transform_pipeline", trigger=ingest.success)
def transform():
    ...
```

Use `TJobRunContext` to inspect which trigger fired when a job has multiple:

```python
from dlt.hub.run import TJobRunContext

@run.pipeline("transform_pipeline", trigger=[ingest.success, other_job.success])
def transform(run_context: TJobRunContext):
    if run_context["trigger"] == ingest.success:
        ...
```

## Scheduler-driven intervals

For incremental pipelines, declare the overall time range with `interval=`:

```python
@run.pipeline(
    my_pipeline,
    interval={"start": "2026-01-01T00:00:00Z"},
    trigger=trigger.schedule("*/3 * * * *"),
)
def daily_ingest(run_context: TJobRunContext):
    start = run_context["interval_start"]
    end = run_context["interval_end"]
    pipeline.run(my_source(start, end))
```

- `interval.start` is where the data begins; `interval.end` defaults to now
- Each run gets the cron tick that just elapsed as `[interval_start, interval_end]`
- Missed ticks are backfilled automatically (window extends back)
- On refresh, Runtime resets the interval pointer to `interval.start`

## Freshness gates

Prevent a job from running until upstream has completed its interval:

```python
@run.pipeline(
    transform_pipeline,
    trigger=trigger.every("5m"),
    freshness=[daily_ingest.is_fresh],
)
def transform(run_context: TJobRunContext):
    ...
```

Freshness is **not** a trigger. The job still runs on its own schedule, but
skips if upstream isn't done yet. Use for transforms that shouldn't observe
mid-load data.

## Refresh cascade

Control how a refresh signal propagates downstream:

| Policy | Behavior |
|--------|----------|
| `refresh="always"` | Every success cascades refresh to downstream (originator) |
| `refresh="auto"` | Passes through if received (default, transparent) |
| `refresh="block"` | Stops propagation |

A backfill job with `refresh="always"` triggers a full reprocess cascade:

```python
@run.job(
    expose={"tags": ["backfill"], "display_name": "Full backfill"},
    refresh="always",
)
def backfill():
    print("cascading refresh to all downstream jobs")
```

Downstream jobs react via `run_context["refresh"]`:
```python
if run_context["refresh"]:
    pipeline.refresh = "drop_sources"
```

## `@run.job` and `@run.interactive`

- `@run.job` -- general batch work (not bound to a named pipeline):
  ```python
  @run.job(trigger=trigger.schedule("0 * * * *"))
  def run_dq_checks():
      ...
  ```

- `@run.interactive` -- long-running HTTP services (MCP, hosted notebooks or dashboards, REST API):
  ```python
  @run.interactive(interface="mcp", idle_timeout="30m")
  def my_mcp_server():
      from fastmcp import FastMCP
      mcp = FastMCP("tools")
      @mcp.tool
      def hello() -> str:
          return "world"
      return mcp
  ```

## Dependency groups

Install extra packages only for jobs that need them:

```toml
# pyproject.toml
[dependency-groups]
ibis = ["ibis-framework[duckdb]"]
```

```python
@run.pipeline(
    transform_pipeline,
    require={"dependency_groups": ["ibis"]},
)
def transform(run_context: TJobRunContext):
    ...
```

## Timeouts

Set per-job timeout with a string shorthand or explicit dict:

```python
# string shorthand
@run.pipeline("my_pipeline", execute={"timeout": "6h"})
def long_job():
    ...

# explicit with custom grace period
@run.pipeline(
    "my_pipeline",
    execute={"timeout": {"timeout": 7200, "grace_period": 60}},
)
def transform():
    ...
```

Default timeout is 120 minutes. Grace period (default 30s) is the window
for graceful shutdown before hard kill.

## Timezone

Set the timezone for cron interpretation:

```python
@run.pipeline(
    my_pipeline,
    trigger=trigger.schedule("0 0 * * *"),
    require={"timezone": "America/New_York"},
)
def daily_load(run_context: TJobRunContext):
    ...
```

Intervals in `run_context` are always UTC, but align to tick boundaries
in the declared timezone.

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
for graceful shutdown before hard kill. Note `grace_period` nests **inside**
`timeout` (matching `TTimeoutSpec`); it is not a sibling key of `execute`.

A longer timeout raises the ceiling on billable wall-clock, so it spends
run-time budget like a size bump does — **ask the user before changing it**
(**job resources and run-time budget** rule).

## Instance size

Runner resources are set with `require={"instance": {"size": ...}}` (public preview):

```python
@run.pipeline(my_pipeline, require={"instance": {"size": "medium"}})
def heavy_sync():
    ...
```

| Size | vCPU | Memory | Disk | Budget multiplier |
|---|---|---|---|---|
| `small` (default) | 2 | 4 GiB | 500 GB | 1x |
| `medium` | 4 | 8 GiB | 500 GB | 2x |
| `large` | 8 | 16 GiB | 500 GB | 4x |
| `xlarge` | 16 | 32 GiB | 500 GB | 8x |

Decorator-only — there is no toml/env form. Two facts that stop wasted bumps:
**disk is 500 GB on every tier**, so sizing up never fixes `Errno 28 No space
left on device`; and **break-even** on `small` → `medium` (2×) needs wall-clock
to drop by **≥50%**, or the bigger box is a net budget loss.

Verify the table against the reference before quoting it to a user — instance
sizing is in public preview and the multipliers may change.

**STOP — never set or change this without explicit human permission.** The
multiplier is charged against the organization's run-time budget on every run,
forever. Propose it with the budget math (current vs proposed multiplier,
wall-clock per run, cadence, resulting charged hours per month), then wait for an
explicit yes for that one job. Same for `execute={"timeout": ...}` and trigger
cadence. The **job resources and run-time budget** rule is always loaded and it governs.

**Do not raise this to fix a slow or OOM-ing job before the pipeline itself is
tuned.** Hand over to the **performance** toolkit (`optimize-performance`,
Step 4) to diagnose the stage bottleneck and check the gate first; install if
absent: `uv run dlthub --non-interactive ai toolkit install performance`.

Reference: https://dlthub.com/docs/hub/pipeline-operations/job-configuration#instance-size

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

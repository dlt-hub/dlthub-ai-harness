# Job patterns

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/triggers.md |
https://dlthub.com/docs/hub/pipeline-operations/job-configuration.md

## Follow-up jobs

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

A local job run does not start the next job in the chain. Run each job with `dlthub local run`.

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
- On refresh, the interval starts again at `interval.start`
- Locally, `dlthub local run <job> --start <ISO 8601> --end <ISO 8601>` gives the interval

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

## Refresh runs and the refresh cascade

A **refresh run** carries the refresh signal: a request to reload the job's data. Start one locally with
`dlthub local run <job> --refresh`. A deployment starts one with `--refresh` on `job run` or `job trigger`: the
platform toolkit gives the command. CLI reference: https://dlthub.com/docs/hub/command-line-interface.md

A refresh run drops or truncates data in the destination. Confirm with the user before you start one, and never
start one on a remote profile without their explicit OK.

### Reload every pipeline in the job (recommended)

`auto_refresh_pipeline_mode` applies a refresh mode to every `dlt.pipeline()` that the job creates, in refresh runs only:

```python
@run.pipeline("my_pipeline", auto_refresh_pipeline_mode="drop_sources")
def ingest():
    pipeline = dlt.pipeline(pipeline_name="my_pipeline", destination="warehouse")
    pipeline.run(my_source())
```

`@run.job` takes it too. Or set it in config, for one job or for all jobs:

```toml
[jobs.<section>.<job_name>]   # the job ref, see deployment-module.md "Job references"
auto_refresh_pipeline_mode = "drop_sources"

[jobs]                        # every job
auto_refresh_pipeline_mode = "drop_data"
```

| Mode | What a refresh run does to each pipeline |
|------|------------------------------------------|
| `drop_sources` | drops the tables and state of every source in the run and resets their schemas |
| `drop_resources` | drops the tables and state of the resources in the run, keeps source-level state |
| `drop_data` | truncates the tables of the resources in the run and resets their state, keeps the schema |

An explicit `refresh=` on `dlt.pipeline()` still wins. The job runs need dlt 1.30.1a0 or later, on this machine
and in the deployment. Without the setting, a refresh run does not reload any pipeline, unless the job code reads
the signal itself (below).

### The same by hand (illustration)

This is what `auto_refresh_pipeline_mode` does for you. Write it out only when pipelines in one job need different handling:

```python
@run.pipeline("my_pipeline")
def ingest(run_context: TJobRunContext):
    pipeline = dlt.pipeline(pipeline_name="my_pipeline", destination="warehouse")
    if run_context["refresh"]:
        pipeline.refresh = "drop_sources"
    pipeline.run(my_source())
```

### Cascade to downstream jobs

`refresh_propagation` decides whether the signal reaches the jobs that follow this one (`trigger=<job>.success`):

| Policy | Behavior |
|--------|----------|
| `refresh_propagation="auto"` | passes the signal on if this run received it (default) |
| `refresh_propagation="always"` | every successful run sends the signal to its direct downstream jobs (originator) |
| `refresh_propagation="block"` | stops propagation. `--refresh` on this job is ignored with a warning |

`refresh=` is the deprecated name of `refresh_propagation=`. A deployment warns about a job that sets
`auto_refresh_pipeline_mode` together with `refresh_propagation="block"`, because block prevents its refresh runs.

A backfill job with `refresh_propagation="always"` triggers a full reprocess cascade. Downstream jobs with
`auto_refresh_pipeline_mode` reload their pipelines:

```python
@run.job(
    expose={"tags": ["backfill"], "display_name": "Full backfill"},
    refresh_propagation="always",
)
def backfill():
    print("cascading refresh to all downstream jobs")
```

A local job run does not start the downstream jobs, so the cascade shows only in a deployment.

## `@run.job` and `@run.interactive`

- `@run.job` -- general batch work (not bound to a named pipeline):
  ```python
  @run.job(trigger=trigger.schedule("0 * * * *"))
  def run_dq_checks():
      ...
  ```

- `@run.interactive` -- long-running HTTP services (MCP, hosted notebooks or dashboards, REST API).
  Serve the job locally with `dlthub local serve <job>`:
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

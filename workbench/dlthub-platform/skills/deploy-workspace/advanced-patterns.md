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

## Background agents

An installed agent definition becomes a job by naming it:

```python
inspector = run.agent(
    "dlthub-platform:job-inspector",
    trigger="job.fail:tag:ingest",       # narrower than the definition's default
    model="anthropic:claude-sonnet-5",   # or azure:<deployment>; the definition pins none
)
```

The job is named after the definition (`job_inspector`), and every decorator argument
overrides the matching `defaults` in the `AGENT.md`.

Decorate a function instead when code has to run around the loop. The evaluator for the
inspector does that: it computes its deterministic checks before the loop and writes them
over the model's output after it.

```python
import sys
from typing import Annotated

from dlt.hub import run

sys.path.insert(0, ".claude/dlthub/agents/job-inspector-eval")
from checks import DEFAULT_MAX_RUNS_READ, finalize, prepare

# `section` is explicit because `.success` and `.fail` are read at import time, before the
# manifest loader stamps the module; without it the trigger names `jobs.job_inspector`
inspector = run.agent(
    "dlthub-platform:job-inspector",
    section="__deployment__",
    trigger="job.fail:tag:ingest",
)


@run.agent(
    agent="dlthub-platform:job-inspector-eval",
    trigger=[inspector.success, inspector.fail],
    model="anthropic:claude-sonnet-5",   # or azure:<deployment>
)
async def job_inspector_eval(
    run_context: run.TJobRunContext = None,
    inspector_run_id: Annotated[
        str,
        run.Entity("job-run"),
        run.Doc("run id of the job-inspector run to evaluate; empty on a trigger"),
    ] = "",
    inspector_job_ref: Annotated[
        str,
        run.Entity("job"),
        run.Doc("job ref of the inspector job; its latest run is evaluated without a run id"),
    ] = "",
    max_runs_read: Annotated[
        int,
        run.Doc("distinct runs the inspector may read before `single_run_scope` fails"),
    ] = DEFAULT_MAX_RUNS_READ,
) -> dict:
    prep = prepare(
        run_context,
        inspector_run_id=inspector_run_id,
        inspector_job_ref=inspector_job_ref,
        max_runs_read=max_runs_read,
    )
    if prep.aborted:
        # raising, not returning: dlt reads `loop.trace` on any dict carrying `status`,
        # and this path never started the loop
        raise run.JobAbortedException(prep.abort_reason, prep.aborted_output)
    output = await run_context["ai_loop"].run(inputs=prep.judge_inputs)
    return finalize(output, prep)
```

A job factory exposes `.success` and `.fail`, so a follow-up job lists them as its trigger.
The scheduler sets `prev_run_id` on the follow-up run, which is how the evaluator finds the
run that triggered it. Both are read at import time, before the manifest loader stamps the
module on the factory, so a factory whose triggers are used in the same module passes
`section=` itself; without it the manifest is rejected with `triggers referencing unknown
jobs`.

Four constraints on the function form, because the function overrides the `AGENT.md` it
drives:

- No docstring, or it replaces the body of the `AGENT.md`.
- Return `dict`, not `TAgentOutput`, or it replaces the declared output schema.
- Declare a parameter for every input a caller may set. Configured inputs reach a decorated
  function through its signature only, and `dlthub deploy` warns about a declared input the
  signature does not accept.
- Raise `run.JobAbortedException` on a path that never started the loop. dlt reads
  `loop.trace` on any returned dict carrying `status`, so returning one there fails the run
  with `AgentTraceNotAvailable` and loses the abort reason.

A shipped agent definition names no model, so pin one: `model=` on the job, or
`AGENT__MODEL` as a workspace variable for all of them. `AGENT__MODEL` overrides a `model=`
on the job, so a workspace that sets it decides for every agent job whatever the code says.
Both take a `provider:model` id on any provider, and an alias (`sonnet`, `gpt-mini`,
`gemini`) where the provider has one. Azure takes `azure:<deployment>` with `AGENT__API_URL`
and `AGENT__API_VERSION` beside the key. The inspector and its evaluator both want a model at
least as capable as Claude Sonnet 5.

Reference: https://dlthub.com/docs/hub/agents/agent-definitions.md

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

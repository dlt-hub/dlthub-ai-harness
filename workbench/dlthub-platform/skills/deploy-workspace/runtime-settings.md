# Job runtime settings

What a job needs from the runner. The job composition patterns are in
[advanced-patterns.md](advanced-patterns.md).

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

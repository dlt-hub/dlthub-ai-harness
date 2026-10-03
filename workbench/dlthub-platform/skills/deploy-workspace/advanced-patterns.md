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
import importlib.util

from dlt.hub import run

# loaded by path under a name of its own: `links` is a common module name, and a `sys.path`
# entry pointing at the agent folder would shadow or be shadowed by another one
_spec = importlib.util.spec_from_file_location(
    "dlthub_agent_links", ".claude/dlthub/agents/job-inspector/links.py"
)
links = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(links)

inspector = run.agent(
    "dlthub-platform:job-inspector",
    # `ingest` is a tag this workspace puts on its own jobs
    trigger="job.fail:tag:ingest",
    require={"profile": "access"},
    # the summary names runs by uuid; this writes each one as a link to its page
    outputs_validator=links.link_summary,
)
```

The job is named after the definition (`job_inspector`), and every decorator argument
overrides the matching `defaults` in the `AGENT.md`. The `access`, `tools`, `skills` and
`rules` lists come from the `AGENT.md`: on a referenced agent the decorator drops its argument
for them, and on a decorated function the argument replaces the list, every axis included.

`outputs_validator` is called with the model's output before `summary` is read off it, on a
referenced agent and a decorated function alike. `link_summary` in the inspector's `links.py`
returns the output with every run id and job ref in the summary written as a link to its web
UI page, labelled with the run number. Without it the summary is stored as the model wrote
it, a uuid inside a code span. The import fails when `.claude/dlthub/agents/job-inspector/`
is missing, and so does the `"dlthub-platform:job-inspector"` reference beside it: both mean
the toolkit is not installed in the workspace.

**An agent job never runs on `prod`.** Pin `require={"profile": "access"}` on every one of
them. Without it the job runs as a batch job on `prod` and the production credentials land
in its environment. The agent's `access` block decides which tools the model is offered; the
profile decides which credentials the job process holds, so declare both. Work that needs
production write credentials belongs in a pipeline or a plain job that a person wrote.

### Model, credentials and verbosity

A shipped definition names no model, so the workspace sets one for every agent job it runs.
Set these as workspace variables, which reach the runner as environment and override
`.dlt/secrets.toml`:

| Variable | Anthropic | Azure OpenAI |
|---|---|---|
| `AGENT__MODEL` | `anthropic:claude-sonnet-5` | `azure:<deployment name>` |
| `AGENT__API_KEY` | the Anthropic key | the Azure key |
| `AGENT__API_URL` | unset | `https://<resource>.openai.azure.com` |
| `AGENT__API_VERSION` | unset | the api-version your deployment serves |

```bash
printf '%s' '<key>' | dlthub variable set AGENT__API_KEY --secret --workspace
```

Pick a model at least as capable as Claude Sonnet 5: `anthropic:claude-sonnet-5` (`sonnet`),
`openai:gpt-5.4-mini` (`gpt-mini`), `google:gemini-3.5-flash` (`gemini`), or your own Azure
deployment. Step up to `opus`, `gpt` or `gemini-pro` for a check that keeps coming back wrong
after its rubric was fixed. `run.agent` takes `model=` too and configuration outranks it, so
leave it out of the deployment code and the two cannot disagree.

Leave `agent.verbosity` at 1, its default. At 0 the job log drops the tool calls and thoughts
the evaluator reads.

### Code around the loop

Decorate a function instead when code has to run around the loop. The evaluator for the
inspector does that: it computes its deterministic checks before the loop and writes them
over the model's output after it.

Two deployments drive the one definition:

| deployment | trigger | what one job run produces |
|---|---|---|
| scheduled | `schedule:0 7 * * 1` | one report over a window of inspector runs, with a recommendation |
| triggered | `inspector.success`, `inspector.fail` | one grade for the inspector run that just finished |

Deploy the scheduled one unless a grade has to land on each inspection as it happens. Both
make one judge call per graded run, and the schedule caps how many a job run makes at
`max_runs`, grades the window in a single job run, and is the only form that reads a pattern
across runs and recommends a change to the inspector's definition. The triggered form starts
a job run per inspection, with no cap on what a busy day costs. Deploy one or the other: an
inspector watched by both is graded twice.

#### One report over a window

```python
import sys
from typing import Annotated

from dlt.hub import run

sys.path.insert(0, ".claude/dlthub/agents/job-inspector-eval")
from checks import (DEFAULT_BATCH_RUNS, DEFAULT_MAX_RUNS_READ, DEFAULT_WINDOW_DAYS,
                    finalize_batch, judge_runs, judge_window_recommendation, prepare_batch)

# `section` pins the module the job ref names, which is the default `inspector_job_ref` below
inspector = run.agent(
    "dlthub-platform:job-inspector",
    section="__deployment__",
    trigger="job.fail:tag:ingest",
    require={"profile": "access"},
    # `links` is the module the first snippet loads
    outputs_validator=links.link_summary,
)


@run.agent(
    agent="dlthub-platform:job-inspector-eval",
    trigger="schedule:0 7 * * 1",
    require={"profile": "access"},
)
async def job_inspector_eval_batch(
    run_context: run.TJobRunContext = None,
    inspector_job_ref: Annotated[
        str, run.Entity("job"), run.Doc("job ref whose window is evaluated")
    ] = "jobs.__deployment__.job_inspector",
    window_days: Annotated[
        int, run.Doc("fallback window with no deployment history")
    ] = DEFAULT_WINDOW_DAYS,
    max_runs: Annotated[
        int, run.Doc("inspector runs one scheduled job grades")
    ] = DEFAULT_BATCH_RUNS,
    max_runs_read: Annotated[
        int,
        run.Doc("distinct runs the inspector may read before `single_run_scope` fails"),
    ] = DEFAULT_MAX_RUNS_READ,
) -> dict:
    batch = prepare_batch(run_context, inspector_job_ref=inspector_job_ref,
                          window_days=window_days, max_runs=max_runs,
                          max_runs_read=max_runs_read)
    if batch.aborted:
        raise run.JobAbortedException(batch.abort_reason, batch.aborted_output)
    # one run out of budget or out of shape must not cost the rest of the window, and
    # `judge_runs` prints each failure as it happens
    evaluations, degraded = await judge_runs(
        run_context["ai_loop"], batch.preps, tolerate_failures=True
    )
    recommendation = ""
    if evaluations:
        recommendation = await judge_window_recommendation(
            run_context["ai_loop"], evaluations + degraded, batch
        )
    return finalize_batch(evaluations, batch, degraded, recommendation)
```

The window starts where the inspector's definition last changed, so every run in the report
was graded against the instructions it ran under. With no deployment history it falls back to
`window_days`.

`finalize_batch` decides what the job does with the report, so the deployment hands it over
rather than reading it. It returns the report where a judge run completed, prints the report
and returns `{}` on an empty window, and raises `run.JobAbortedException` carrying the report
where the window found runs and no judge run completed.

#### One grade per inspector run

```python
import sys
from typing import Annotated

from dlt.hub import run

sys.path.insert(0, ".claude/dlthub/agents/job-inspector-eval")
from checks import DEFAULT_MAX_RUNS_READ, judge_runs, prepare

# `section` is explicit because `.success` and `.fail` are read at import time, before the
# manifest loader stamps the module; without it the trigger names `jobs.job_inspector`
inspector = run.agent(
    "dlthub-platform:job-inspector",
    section="__deployment__",
    trigger="job.fail:tag:ingest",
    require={"profile": "access"},
    # `links` is the module the first snippet loads
    outputs_validator=links.link_summary,
)


@run.agent(
    agent="dlthub-platform:job-inspector-eval",
    trigger=[inspector.success, inspector.fail],
    require={"profile": "access"},
)
async def job_inspector_eval(
    run_context: run.TJobRunContext = None,
    inspector_run_id: Annotated[
        str,
        run.Entity("job-runs"),
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
    evaluations, degraded = await judge_runs(
        run_context["ai_loop"], [prep], tolerate_failures=True
    )
    if not evaluations:
        # the judge ran out of turns or tokens after Python decided its checks; `judge_runs`
        # kept those rather than lose the run's whole result
        raise run.JobAbortedException(degraded[0]["summary"], degraded[0])
    return evaluations[0]
```

A job factory exposes `.success` and `.fail`, so a follow-up job lists them as its trigger.
The scheduler sets `prev_run_id` on the follow-up run, which is how the evaluator finds the
run that triggered it. Both are read at import time, before the manifest loader stamps the
module on the factory, so a factory whose triggers are used in the same module passes
`section=` itself; without it the manifest is rejected with `triggers referencing unknown
jobs`.

#### Four constraints on the function form

The function overrides the `AGENT.md` it drives, on both deployments:

- No docstring, or it replaces the body of the `AGENT.md`.
- Return `dict`, not `TAgentOutput`, or it replaces the declared output schema.
- Declare a parameter for every input a caller may set. Configured inputs reach a decorated
  function through its signature only, and `dlthub deploy` warns about a declared input the
  signature does not accept.
- Raise `run.JobAbortedException` on a path that never started the loop. dlt reads
  `loop.trace` on any returned dict carrying `status`, so returning one there fails the run
  with `AgentTraceNotAvailable` and loses the abort reason.

A shipped agent definition names no model, so set one for the workspace:

```bash
dlthub variable set AGENT__MODEL --value 'anthropic:claude-sonnet-5' --plain --workspace
```

Every agent job in the workspace reads it. It takes a `provider:model` id on any provider,
and an alias (`sonnet`, `gpt-mini`, `gemini`) where the provider has one. Azure takes
`azure:<deployment>` with `AGENT__API_URL` and `AGENT__API_VERSION` beside the key. The
inspector and its evaluator both want a model at least as capable as Claude Sonnet 5.

`run.agent` takes `model=` too, and configuration outranks it, so a model in the deployment
code is beaten by `AGENT__MODEL` wherever the variable is set. Keep the decision in the
variable.

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

Runtime settings for a job, dependency groups, timeouts, instance size and timezone, are in
[runtime-settings.md](runtime-settings.md).

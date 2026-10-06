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
from dlt.hub import run

inspector = run.agent(
    "dlthub-platform:job-inspector",
    # `ingest` is a tag this workspace puts on its own jobs
    trigger="job.fail:tag:ingest",
    require={"profile": "access"},
)
```

The job is named after the definition (`job_inspector`), and every decorator argument
overrides the matching `defaults` in the `AGENT.md`. The `access`, `tools`, `skills` and
`rules` lists come from the `AGENT.md`: on a referenced agent the decorator drops its argument
for them, and on a decorated function the argument replaces the list, every axis included.

An agent folder can ship an `agent.py`, which dlt 1.30.1a1 and later runs around the loop of a
job that references the agent: `validate_input(inputs)` before it and `validate_output(output)`
after it. A decorated function owns its own run and the module never reaches it. The inspector's
`agent.py` writes every run id and job ref in its summary as a link to its web UI page, labelled
with the run number. The reference fails when
`.claude/dlthub/agents/job-inspector/` is missing, which means the toolkit is not installed in
the workspace.

**An agent job never runs on `prod`.** Pin `require={"profile": "access"}` on every one of
them. Without it the job runs as a batch job on `prod` and the production credentials land
in its environment. The agent's `access` block decides which tools the model is offered; the
profile decides which credentials the job process holds, so declare both. Work that needs
production write credentials belongs in a pipeline or a plain job that a person wrote.

### Model and credentials

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
deployment. Step up to `opus`, `gpt` or `gemini-pro` when a smaller model falls short.
`run.agent` takes `model=` too and configuration outranks it, so leave it out of the
deployment code and the two cannot disagree.

A shipped agent definition names no model, so set one for the workspace:

```bash
dlthub variable set AGENT__MODEL --value 'anthropic:claude-sonnet-5' --plain --workspace
```

Every agent job in the workspace reads it. It takes a `provider:model` id on any provider,
and an alias (`sonnet`, `gpt-mini`, `gemini`) where the provider has one. Azure takes
`azure:<deployment>` with `AGENT__API_URL` and `AGENT__API_VERSION` beside the key. The
inspector wants a model at least as capable as Claude Sonnet 5.

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

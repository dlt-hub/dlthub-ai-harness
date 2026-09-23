# job-inspector

Inspects a failed job run of a dltHub Platform workspace: reads the run record, the logs and
the job definition, classifies the failure and proposes a fix. Read-only. The definition is
[`AGENT.md`](AGENT.md); [`job-inspector-eval`](../job-inspector-eval/README.md) grades its
runs.

## Deploying it

```python
from dlt.hub import run

inspector = run.agent(
    "dlthub-platform:job-inspector",
    trigger="job.fail:tag:ingest",       # narrower than the definition's default
)
```

Name the jobs or tag them. `job.fail:*` expands onto every other job in the workspace, so in
a workspace that also runs the evaluator a failing evaluation would be inspected and the
inspection would start the evaluator again.

Keep `agent.verbosity` at 1, the default. At 0 the log drops tool arguments and thoughts,
and four of the evaluator's checks read them.

## Model

The definition sets no `model`, so it runs on whatever the workspace configures, on any
endpoint the pydantic-ai loop supports. The inspector reads a log it cannot fit in one turn,
holds a hypothesis across tool calls and answers with a structured diagnosis, so give it a
model at least as capable as Claude Sonnet 5.

| Provider | Model meeting the bar | Alias | Step up when needed |
|---|---|---|---|
| Anthropic | `anthropic:claude-sonnet-5` | `sonnet` | `opus` |
| OpenAI | `openai:gpt-5.4-mini` | `gpt-mini` | `gpt` (`gpt-5.5`) |
| Azure OpenAI | `azure:<your deployment>` | none | a larger deployment |
| Google | `google:gemini-3.5-flash` | `gemini` | `gemini-pro` |

Set it through the `AGENT__MODEL` workspace variable, which takes a `provider:model` id on
any provider. An alias works where the provider has one, and Azure has none, because it
addresses a deployment on your own endpoint. `AGENT__MODEL`, `AGENT__API_KEY`,
`AGENT__API_URL` and `AGENT__API_VERSION` are one set: see
[Configuring the endpoint](../job-inspector-eval/README.md#configuring-the-endpoint).

`loop: claude-agent-sdk` takes Anthropic models only. The inspector sets no loop, so it runs
on pydantic-ai and reaches every provider in the table. Naming that loop in a workspace whose
key is Azure or Google breaks the run.

Two checks the evaluator runs depend on the model rather than the inspector: `skill_loaded`
reports `N/A` outside `claude-agent-sdk`, and the checks that read thoughts decide something
only on a model that emits reasoning into the log.

## Running it by hand

```bash
dlthub local run job_inspector -c failed_run_id=<run id>
```

```bash
dlthub local run job_inspector -c failed_job_ref=jobs.my_pipeline
```

Both inputs are optional. Given neither, the agent resolves the run from the trigger that
started it, and aborts when nothing identifies one.

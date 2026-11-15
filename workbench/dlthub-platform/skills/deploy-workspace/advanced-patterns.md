# Advanced Deployment Patterns

Follow-up jobs, intervals, freshness gates, refresh runs and the refresh cascade, `@run.job` and
`@run.interactive` are in `job-patterns.md` of the (`define-and-debug-jobs`) skill (local-workspace toolkit).

## Background agents

An installed agent definition becomes a job by naming it:

```python
from dlt.hub import run

inspector = run.agent(
    "dlthub-platform:job-inspector",
    # `ingest` is a tag this workspace puts on its own jobs
    trigger="job.fail:tag:ingest",
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
`.claude/dlthub/agents/dlthub-platform/job-inspector/` is missing, which means the toolkit is
not installed in the workspace.

**An agent job never gets `prod`.** Declare no profile on it, and keep `write` out of
`access.data` in its agent definition. The deployment then gives it the profile with `none`
data access of its environment. Declare one in every environment that the job deploys to:
`dlthub profile add <env>-none --access none --env <env>`. In `prod` without one, the job gets
`access`, or `prod` while `access` has no settings files, and `dlthub deploy` warns. The agent's `access` block decides which tools the model is
offered; the profile decides which credentials the job process holds. Work that needs
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

Runtime settings for a job, dependency groups, timeouts, instance size and timezone, are in
[runtime-settings.md](runtime-settings.md).

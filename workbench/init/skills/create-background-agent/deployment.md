# Deploying an agent

This file owns turning a definition into an agent job: `run.agent`, the profile pin, triggers, the
decorated form for code around the loop, and the `AGENT__` variables. The definition itself is in
[agent-md-reference.md](agent-md-reference.md).

Reference: deployments `https://dlthub.com/docs/hub/pipeline-operations/deployments.md`, triggers
`https://dlthub.com/docs/hub/pipeline-operations/triggers.md`, job configuration
`https://dlthub.com/docs/hub/pipeline-operations/job-configuration.md`

## From the definition to a job and a run

A workspace turns the definition into an agent job in its deployment module:

```python
from dlt.hub import run

inspector = run.agent(
    "dlthub-platform:job-inspector",
    # access comes from the definition: local: [read], context: [read]. an `access=`
    # argument on a referenced agent is dropped; see below
    # `ingest` is a tag this workspace puts on its own jobs
    trigger="job.fail:tag:ingest",
    require={"profile": "access"},       # see "Profile"
    instructions="focus on the loader step",
)
```

`trigger` takes dlt trigger strings: `schedule:0 7 * * *`, `job.fail:<job ref or selector>`,
`job.success:...`. `job.fail:*` watches every job in the workspace and expands at manifest time,
never onto the job that declares it; read "Triggers that would loop" below before using it. A run
started by hand or from the UI arrives with a `manual:` trigger and only the inputs it was given,
which is why the body must say what to do with empty input.

Every decorator argument overrides the matching `defaults`, and configuration overrides both;
`instructions` is the user turn of every run. The job takes the definition's name,
`job_inspector` here. Instead of a `<toolkit>:<name>` reference the workspace may point at a
folder holding an `AGENT.md` by its workspace-relative path.

`access`, `tools`, `skills` and `rules` are not defaults. A referenced agent keeps the
definition's lists and the decorator drops its arguments for them. A decorated function driving a
referenced agent replaces the definition's list with the argument, so `access={"local": ["read"]}`
on such a function removes `context: read`. Pass every axis the agent needs, or leave the block to
the definition.

## Profile

**An agent job never runs on `prod`.** Pin the read-only profile on every one of them with
`require={"profile": "access"}`. Without this pin, an agent job is a batch job on `prod` and gets
production credentials in its environment. Declare the profile alongside the `access` block:
`access` decides which tools the model is offered; the profile decides which credentials the job
process holds.

The pin governs profile-scoped credentials: `prod.secrets.toml`, `prod.config.toml`, and a
variable set with `dlthub variable set --profile prod`. A variable set with `--workspace` has no
profile and reaches the job whatever it runs on, so a secret that must stay away from an agent
belongs in a profile scope rather than the workspace scope. `dlthub variable list` prints the
scope of each one in its `Profile` column.

Work that needs production write credentials belongs in a pipeline or a plain job, which a person
wrote and reviewed, and an agent proposes it rather than performing it.

Nothing at deploy time enforces this. Manifest validation rejects a local-only profile (`dev`,
`tests`) and otherwise takes the name as given: `prod` passes, and so does a typo like `acess`,
which then surfaces as missing credentials at run time. The rule holds because authors apply it,
and an evaluator catches a break after the fact by reading the profile off the run record.

The profile has to be `configured` in the workspace; workspace info lists which ones are. On
`dlthub local run` the declaration is a warning rather than a switch: the run uses the active
profile and reports the mismatch, so check the active profile before running an agent job by hand.

## Running a job by hand

```bash
dlthub local run job_inspector -c failed_run_id=89826ee6-... -c agent.instructions="explain, do not fix"
```

Inputs, instructions, verbosity, model and limits are all job configuration under the job's
section, so the same keys work in `config.toml`, the environment, the command line, and the web
UI's run dialog. What comes back is a job result: `status` and `summary` lifted to the top,
`result` as the output schema declares it, `object` with the entities the run acted on, and a
`trace` of model, limits, inputs, tools used, turns and tokens. The transcript of the run prints
to the job's log at the configured verbosity.

Keep `agent.verbosity` at 1, the default. At 0 the log keeps tool names only, and anything reading
the agent's tool arguments or statements afterwards goes blind.

## Code around the loop

Work that has to happen before the loop and again after it has no seam in the declared form. A
function decorated with `run.agent(agent="<toolkit>:<agent>")` does: it keeps the referenced
definition's prompt and schemas, and owns the run.

```python
import sys
from typing import Annotated

from dlt.hub import run

sys.path.insert(0, ".claude/dlthub/agents/<agent>")
from helpers import after, before


@run.agent(
    agent="<toolkit>:<agent>",
    trigger="schedule:0 7 * * *",
    require={"profile": "access"},
)
async def graded_agent(
    run_context: run.TJobRunContext = None,
    target_run_id: Annotated[
        str,
        run.Entity("job-run"),
        run.Doc("run id to work on; empty on a trigger"),
    ] = "",
) -> dict:
    prep = before(run_context, target_run_id=target_run_id)
    if prep.aborted:
        # raising, not returning: dlt reads `loop.trace` on any dict carrying `status`,
        # and this path never started the loop
        raise run.JobAbortedException(prep.abort_reason, prep.aborted_output)
    answer = await run_context["ai_loop"].run(inputs=prep.inputs)
    return after(answer, prep)
```

The function overrides the definition it drives, so watch the signature. Give it **no docstring**,
since a docstring replaces the body. Return **`dict` rather than `TAgentOutput`**, since a return
type deriving from `TAgentOutput` replaces the output schema with the bare `status` and `summary`.
Take **a parameter for every input a caller may set**, since configured inputs reach a decorated
function through its signature only, and an input declared in the `AGENT.md` but absent from the
signature is warned about at deploy time and nothing passes it. Inputs the code supplies itself
stay out of the signature and travel through `loop.run(inputs=...)`; the `AGENT.md` declares them
because a body placeholder must be declared.

A path that never started the loop raises rather than returns. dlt reads `loop.trace` on any
returned dict carrying `status`, so returning one from the abort branch fails the run with
`AgentTraceNotAvailable` and loses the abort reason. A loop that started and then raised is the
same case: it records its trace only on the way out of a normal return, so a degraded result goes
out through `JobAbortedException` too.

`.success` and `.fail` are read at import time, before the manifest loader stamps the module on
the factory, so an agent whose triggers are used in the same module sets `section=` itself.
Without it the trigger names `jobs.<job name>` and the manifest is rejected with `triggers
referencing unknown jobs`.

An agent folder travels as ordinary workspace files, so supporting code sits next to the
`AGENT.md` and the deployment reaches it through `sys.path`. The runner unpacks it under the run
directory, so the same relative path works there.

Code that talks to the platform reads dlt's own `active().runtime_config` for the credential
(`api_key` or `auth_token`, `workspace_id`, `api_base_url`) rather than the environment. The same
call resolves from `.dlt/config.toml` locally and from the mounted configuration on the runner, so
there is nothing to guess about which keys the platform injects.

The JWT that `dlthub login` writes expires after about an hour, so a fetcher passes a credentials
object the SDK renews through. A static token makes a long run fail halfway with `token_expired`.

## Triggers that would loop

Do not point an inspecting agent at `job.fail:*` in a workspace that runs an evaluator. The
selector expands onto every other job, the evaluator included, so a failing evaluation is
inspected and the inspection starts the evaluator again. Name the jobs, or tag them. A tag that
matches no job is reported at deploy time as `matched no job`.

Three mechanisms sit between a broad selector and a loop, and none of them replaces naming the
jobs: the inspecting agent aborts when the run it resolved belongs to an evaluator job or to its
own job; `no_agent_job_inspected` reports FALSE when an inspection reached one anyway, so the loop
shows up in the evaluation; a job event never fires on a manual run. dlt has no manifest
validation for this yet, because a selector is expanded to concrete refs at deploy time and
nothing compares the result against the jobs that run agents.

## Pinning the model

An agent names no model, so the workspace sets one. `agent.model`, `agent.api_key`, `agent.api_url`
and `agent.api_version` are one set: a run takes all four from the workspace or all four from the
runtime. Setting `api_key` alone leaves `model` unset, so the run sends the agent's default model
to your endpoint and gets `401 API key is invalid`. Set them as workspace variables, which arrive
on the runner as environment and override `.dlt/secrets.toml`:

```bash
printf '%s' '<key>' | dlthub variable set AGENT__API_KEY --secret --workspace
```

| Variable | Anthropic | Azure OpenAI |
|---|---|---|
| `AGENT__MODEL` | `anthropic:claude-sonnet-5` | `azure:<deployment name>` |
| `AGENT__API_KEY` | the Anthropic key | the Azure key |
| `AGENT__API_URL` | unset | `https://<resource>.openai.azure.com` |
| `AGENT__API_VERSION` | unset | the api-version your deployment serves |

Azure is the only provider pydantic-ai gives `api_version`. On the rest it is ignored with a
warning, so leave it unset.

`AGENT__MODEL` takes a `provider:model` id on any provider, and an alias where the provider has
one. Which model meets the bar is a property of the instructions: say in the `AGENT.md` what class
of model they were written for. The agents in this repo were written for a model at least as
capable as Claude Sonnet 5.

| Provider | Model meeting that bar | Alias | Step up when needed |
|---|---|---|---|
| Anthropic | `anthropic:claude-sonnet-5` | `sonnet` | `opus` |
| OpenAI | `openai:gpt-5.4-mini` | `gpt-mini` | `gpt` (`gpt-5.5`) |
| Azure OpenAI | `azure:<your deployment>` | none | a larger deployment |
| Google | `google:gemini-3.5-flash` | `gemini` | `gemini-pro` |

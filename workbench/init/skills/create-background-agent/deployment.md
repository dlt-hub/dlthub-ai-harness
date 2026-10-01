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

`instructions` is the user turn of every run. The job takes the definition's name, `job_inspector`
here. Instead of a `<toolkit>:<name>` reference the workspace may point at a folder holding an
`AGENT.md` by its workspace-relative path.

## What the Python definition overrides

Four places set a field. Each one overrides the one before it:

1. the `AGENT.md`
2. the `run.agent(...)` arguments
3. the decorated function's name, docstring, signature and return type
4. job configuration under `[jobs.<module>.<job>.agent]`, with inputs one level up in
   `[jobs.<module>.<job>]`

Where the Python and the file both set a field, the Python wins and the file's value is never
read. The `AGENT.md` is the agent as shipped and the deployment module is the agent as it runs,
so read the module to see what a run was given.

| `AGENT.md` field | `run.agent("<ref>", ...)` | `@run.agent(agent="<ref>", ...)` on a function |
|---|---|---|
| body (system prompt) | no argument for it, the file stands | the docstring replaces it |
| `description` | the file stands | the docstring's first line replaces it |
| `name` | the job takes the agent's name | the job takes the function's name |
| `inputs` | the file stands | the signature's parameters are written over the file's |
| `output` | the file stands | a return type deriving from `TAgentOutput` replaces it, `dict` leaves the file's |
| `access`, `tools`, `skills`, `rules` | the argument is dropped, the file stands | the argument replaces the file's list |
| `defaults` (`model`, `limits`, `loop_run_args`) | the matching argument overrides that key | the matching argument overrides that key |

`access`, `tools`, `skills` and `rules` are not `defaults`, which is why the two forms differ on
them. On a decorated function the argument replaces the whole list, so `access={"local": ["read"]}`
removes `context: read`. Pass every axis the agent needs, or leave the block out and let the
definition hold it. `status` and `summary` are written over whatever `output` ends up being, in
both forms.

A decorated function needs no `agent=` at all. With none the function is the whole definition and
there is no `AGENT.md`: the docstring is the system prompt, the parameters are the inputs, the
return type is the output, and the agent is referred to as `<module>:<function>`. The agents in
this repo keep a file so a toolkit can install the definition and a grader can read it.

## Profile

**An agent job must never run on the `prod` profile.** The runtime gives an agent job the
read-only `access` profile when the deployment declares none. A deployment can override that with
`require={"profile": ...}`, and pointing it at `prod` puts production credentials in the job
process, so leave it at `access`.

Pin `require={"profile": "access"}` anyway. The declaration then says which profile the job runs
on, and `dlthub local run` reports a mismatch with the active one. Declare it beside the `access`
block. `access` decides which tools the model is offered. The profile decides which credentials
the job process holds.

The pin governs profile-scoped credentials: `prod.secrets.toml`, `prod.config.toml`, and a
variable set with `dlthub variable set --profile prod`. A variable set with `--workspace` has no
profile and reaches the job whatever it runs on, so a secret that must stay away from an agent
belongs in a profile scope rather than the workspace scope. `dlthub variable list` prints the
scope of each one in its `Profile` column.

Work that needs production write credentials belongs in a pipeline or a plain job, which a person
wrote and reviewed, and an agent proposes it rather than performing it.

Nothing at deploy time rejects an explicit `prod`. Manifest validation rejects a local-only
profile (`dev`, `tests`) and otherwise takes the name as given, so a typo like `acess` passes too
and surfaces as missing credentials at run time. An evaluator catches a break after the fact by
reading the profile off the run record.

The profile has to be `configured` in the workspace; workspace info lists which ones are. On
`dlthub local run` the declaration is a warning rather than a switch: the run uses the active
profile and reports the mismatch, so check the active profile before running an agent job by hand.

## Running an agent job by hand

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

The declared form leaves no place for code that has to run before the loop and again after it.
Decorate a function with `run.agent(agent="<toolkit>:<agent>")` instead. The function owns the run
and keeps the referenced definition's prompt and schemas.

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

The function overrides the definition it drives, as "What the Python definition overrides" sets
out above, so watch the signature. Give it **no docstring**,
since a docstring replaces the body. Return **`dict` rather than `TAgentOutput`**, since a return
type deriving from `TAgentOutput` replaces the output schema with the bare `status` and `summary`.
Take **a parameter for every input a caller may set**, since configured inputs reach a decorated
function through its signature only, and an input declared in the `AGENT.md` but absent from the
signature is warned about at deploy time and nothing passes it. Inputs the code supplies itself
stay out of the signature and travel through `loop.run(inputs=...)`; the `AGENT.md` declares them
because a body placeholder must be declared.

Raise `JobAbortedException` on any path that did not complete a loop run. dlt reads `loop.trace`
on every returned dict carrying `status`, so returning from the abort branch fails the run with
`AgentTraceNotAvailable` and loses the abort reason. The loop records its trace on the way out of
a normal return, so a loop that started and then raised takes the same path.

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

An agent definition names no model, so the workspace sets one. `agent.model`, `agent.api_key`,
`agent.api_url` and `agent.api_version` are one set: a run takes all four from the workspace or
all four from the runtime. Setting `api_key` alone leaves `model` unset, so the run sends the
agent's default model to your endpoint and gets `401 API key is invalid`. Set them as workspace
variables, which arrive on the runner as environment and override `.dlt/secrets.toml`:

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
one. Instructions are written for a class of model, so say in the `AGENT.md` which class. The
agents in this repo need a model at least as capable as Claude Sonnet 5.

| Provider | Smallest model that fits | Alias | Larger model |
|---|---|---|---|
| Anthropic | `anthropic:claude-sonnet-5` | `sonnet` | `opus` |
| OpenAI | `openai:gpt-5.4-mini` | `gpt-mini` | `gpt` (`gpt-5.5`) |
| Azure OpenAI | `azure:<your deployment>` | none | a larger deployment |
| Google | `google:gemini-3.5-flash` | `gemini` | `gemini-pro` |

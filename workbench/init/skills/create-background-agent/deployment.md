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
    # `access=` on a referenced agent is dropped; the definition holds the grant
    # `ingest` is a tag this workspace puts on its own jobs
    trigger="job.fail:tag:ingest",
    require={"profile": "access"},       # see "Profile"
    instructions="focus on the loader step",
)
```

`trigger` takes dltHub trigger strings: `schedule:0 7 * * *`, `job.fail:<job ref or selector>`,
`job.success:...`. `job.fail:*` watches every job in the workspace and expands at manifest time,
never onto the job that declares it; read "Triggers that would loop" below before using it. A run
started by hand or from the UI arrives with a `manual:` trigger and only the inputs it was given,
which is why the body must say what to do with empty input.

`instructions` is the user turn of every run. The job takes the definition's name, `job_inspector`
here. Instead of a `<toolkit>:<name>` reference the workspace may point at a folder holding an
`AGENT.md` by its workspace-relative path. A path reference then needs `name=` as well: the job
name comes from the reference, and `agents/job-inspector` is no Python identifier, so without it
the deployment fails with `InvalidJobName`.

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
read-only `access` profile when the deployment does not declare a profile. A deployment can override that with
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
and surfaces as missing credentials at run time. The run record carries the profile the run
used, so a break shows up there after the fact.

The profile has to be `configured` in the workspace; workspace info lists which ones are. On
`dlthub local run` the declaration is a warning rather than a switch: the run uses the active
profile and reports the mismatch, so check the active profile before running an agent job by hand.

## Running an agent job by hand

The loop is an optional dependency. A local machine installs it once:

```bash
pip install "pydantic-ai-slim[anthropic,openai,google,mcp,spec]"
```

Without it the run stops at `MissingDependencyException` before the model is addressed.

The runner takes it from the `agent-loop-pydantic-ai` group, which dltHub adds to the workspace
requirements with that same spec and no version bound. A workspace whose other pins push the
solver backwards gets an old loop that fails to import, so pin a floor of your own next to the
rest of the workspace dependencies:

```text
pydantic-ai-slim>=2.52.0
```

**A local run does not get the secret workspace variables.** Plain ones sync down and resolve, so
`AGENT__MODEL` is there, and `AGENT__API_KEY` and a destination password are not. The run then
falls back to the loop's default model with no key and dies inside the provider at `_build_model`,
on `Set the ANTHROPIC_API_KEY environment variable`, which names a variable the workspace never
used. The only way through is the person at the keyboard exporting the secrets into their own
shell:

```bash
export AGENT__API_KEY=<the provider key>
```

Do not orchestrate that for them, and do not read it back: it is a secret in the session, which
the `setup-secrets` rules forbid. Ask them to export it and say when it is set. Where that is
awkward, check the agent offline instead, below.

```bash
dlthub local run job_inspector -c failed_run_id=89826ee6-... -c agent.instructions="explain, do not fix"
```

Inputs, instructions, verbosity, model and limits are all job configuration under the job's
section, so the same keys work in `config.toml`, the environment, the command line, and the web
UI's run dialog. What comes back is a job result: `status` and `summary` lifted to the top,
`result` as the output schema declares it, `object` with the entities the run acted on, and a
`trace` of model, limits, inputs, tools used, turns and tokens. The transcript of the run prints
to the job's log at the configured verbosity.

A deployed run delivers the same job result to the platform, and **dlt 1.31.0** is where it
arrives: before that it was dropped at ingest, so a run on the platform had no summary, output or
trace to show in the web app, CLI or MCP. Read it back with the run id or the job name:

```bash
dlthub job runs result <run id> --json
```

`--only-payload` prints the `result` object alone, which is the agent output against the schema
the `AGENT.md` declares. `dlthub_get_run_result` is the same artifact through the MCP server.

Keep `agent.verbosity` at 1, the default. At 0 the log keeps tool names only, and anything reading
the agent's tool arguments or statements afterwards goes blind.

## Check it offline, before it costs a run

Three calls exercise a definition without a provider key and without spending a token. Run them
before the first deployed run, and again whenever the frontmatter changes.

Check `dlthub --version` first. The three calls below are written for **dlt 1.31.0**, and run
unchanged on 1.30.1a1: both have `load_agent_module`, and on both a declared agent job returns a
coroutine. On 1.30.1a0 the second call raises `ImportError` and the third raises
`RuntimeError: asyncio.run() cannot be called from a running event loop`; that version runs the
loop synchronously through `run_declared_agent`, and "On dlt 1.30.1a0" below has the shape that
works there.

**The spec.** `load_agent_spec` reads the `AGENT.md` and holds it to the contract, so a bad
`access` verb, an empty body or an `inputs.prompt` fails here rather than at manifest time.

```python
from dlt._workspace.deployment.agent.manifest import load_agent_spec

spec = load_agent_spec("agents/<name>")
```

**The hooks.** `load_agent_module` imports the agent's `agent.py` the way a run does, under a
private package named after a hash of the folder. That is why `from .coverage import collect`
works inside it and a plain `importlib` load of the same file does not, and why a hyphenated
folder name is importable here and nowhere else. Call it to test your own hook code. It needs
**dlt 1.30.1a1 or later**: below that the name is not in
`dlt._workspace.deployment.agent.manifest` at all and the import raises an `ImportError` that
says nothing about versions, and a workspace on an older pin attaches its hooks through
`run.agent(inputs_validator=..., outputs_validator=...)` instead.

```python
from dlt._workspace.deployment.agent.manifest import load_agent_module

module = load_agent_module("agents/<name>")
assert module.validate_input({"audit_date": "2026-10-01"})["coverage"]
```

**The whole loop, with the model answered offline.** Subclass `PydanticAILoop`, return
pydantic-ai's `TestModel` from `_build_model`, register the subclass through the `plug_agent_loop`
plugin hook, and name its `LOOP_TYPE` in `loop=` on the job. The run then exercises the input
hook, the placeholder substitution, the inlined rules and skills, the local tool wiring and the
output schema, and `TestModel` fills the output from the declared schema so dltHub validates it in
full.

`trace["local_tools"]` is what the `access` block wired, computed from the grant, so the assertion
below is the one that catches a verb you did not mean to give. `trace["mcp_features"]` repeats the
`tools` list from the file and says nothing about the server.

The run below never starts a server: `_build_toolsets` returns `[]`, which keeps the check offline
and quick, and it is what the harness repo's `tests/agents/conftest.py` does. Drop that override
and the real workspace MCP server starts over stdio. The trace reads the same either way, so the
evidence is in the transcript: the server's own banner names the features it assembled and the
access it was handed, and the loop prints `dlt-workspace-mcp connected`. That is how to check the
server command resolves and the groups register. `TestModel(call_tools=[])` still keeps the model
from calling anything.

Both halves are needed. `resolve_agent_loop` asks the registered plugins for a class answering to
the loop type, so a subclass nobody registered is never reached and `loop="null-pydantic-ai"`
raises `UnknownAgentLoop`. Leave `loop=` off and the job takes the default `pydantic-ai`, which
addresses the real provider: the section runs against a live key, or dies on
`Set the ANTHROPIC_API_KEY environment variable`.

Run this as a script from the workspace root:

```python
import asyncio

from pydantic_ai.models.test import TestModel

from dlt.common.configuration.plugins import hookimpl, manager
from dlt._workspace.deployment.agent.loops.pydantic_ai import PydanticAILoop
from dlt.hub import run


class NullModelLoop(PydanticAILoop):
    LOOP_TYPE = "null-pydantic-ai"

    def _build_model(self):
        return TestModel(call_tools=[])

    def _build_toolsets(self):
        return []


class NullModelLoopPlugin:
    @hookimpl(specname="plug_agent_loop")
    def plug_agent_loop(self, loop_type):
        return NullModelLoop if loop_type == NullModelLoop.LOOP_TYPE else None


manager().register(NullModelLoopPlugin(), name="null-model-loop")

job = run.agent("<toolkit>:<name>", loop=NullModelLoop.LOOP_TYPE)


async def main():
    report = await job(**inputs)
    trace = job.last_job_result["trace"]

    # the one assertion that pays for this section: a placeholder the run did not resolve
    # rendered as empty text, and the agent read a sentence with a hole in it
    assert trace["unresolved_placeholders"] == []
    # `agent.loop` config overrides the `loop=` argument, so check which loop actually ran
    assert trace["loop_type"] == NullModelLoop.LOOP_TYPE
    assert trace["local_tools"] == {"Read": "read", "Glob": "read", "Grep": "read"}
    assert trace["inlined_skills"] == ["<toolkit>:<skill>"]
    assert report["status"] == "succeeded"


asyncio.run(main())
```

On dlt 1.31.0 and 1.30.1a1 a declared `run.agent("<ref>")` returns a coroutine when called, so the
call is awaited, and it returns the agent output: the job result sits on `job.last_job_result`
beside it. A decorated function returns a coroutine only when it is `async def`.

**On dlt 1.30.1a0** the same call is synchronous and returns the whole job result, `trace`
included, and `last_job_result` is not an attribute of `AgentJobFactory`. Drop the `async def` and
the `asyncio.run`, and read the trace off the return value:

```python
result = job(**inputs)
trace = result["trace"]
report = result["result"]
```

Assert `unresolved_placeholders` on every agent. It is empty only when every `{{ ... }}` in the
body was filled by this run's inputs, so it catches a typo, a renamed input, and a
`run_context` field the trigger does not carry. The deployed run that finds the same thing costs
a full token budget.

The AI harness repo wires the same loop into pytest in `tests/agents/conftest.py`, where the
plugin registers on `Container()[PluginContext].manager` and the loop type comes from an
`AGENT__LOOP` environment variable rather than `loop=`. A fixture there installs the toolkit into
a temporary workspace, and `tests/agents/test_agents_run.py` is the shape of a test over it.

## Row evidence through a hook

An agent folder ships an `agent.py` beside its `AGENT.md`. From dlt 1.30.1a1 dltHub imports that
module on a declared `run.agent("<ref>", ...)` and calls `validate_input(inputs)` before the loop
and `validate_output(output)` after it. A returned value replaces the inputs or the output,
`None` keeps them, and raising `JobAbortedException` from `validate_input` ends the run before the
loop starts. This is where an agent reads warehouse rows, since the MCP data tools need pipeline
state a runner has not got; see the `data` axis in
[agent-md-reference.md](agent-md-reference.md).

`run.agent(inputs_validator=..., outputs_validator=...)` does not replace the module's hooks, it
runs after them: `_collect_validators` returns the one from `agent.py` first and the one the job
passed second. So an agent folder shipping an `agent.py` passes neither argument, or its hook runs
twice on every run. For a hook that queries a warehouse that is every query twice, with nothing in
the log to say so.

`agents/<name>/coverage.py`, resolving the date column against the schema rather than guessing it:

```python
import dlt


def collect(audit_date, tables):
    destination = dlt.config["destination.name"]
    for dataset_name in {t.dataset for t in tables}:
        dataset = dlt.dataset(destination=destination, dataset_name=dataset_name)
        known = {name.lower() for name in dataset.schema.tables}
        # a table the warehouse does not carry is a note in the window, not a row count of zero
```

`agents/<name>/agent.py` beside it:

```python
from .coverage import TABLES, collect, render


def validate_input(inputs):
    audit_date = inputs.get("audit_date") or str(
        (inputs.get("run_context") or {}).get("interval_start")
    )[:10]
    return {**inputs, "audit_date": audit_date, "coverage": render(collect(audit_date, TABLES))}
```

The `AGENT.md` declares `coverage` as an input described as never set by a caller, and the body
renders `{{ coverage }}` into a section saying it is the only row evidence the agent has. A body
placeholder must be declared, which is why the input is in the file although nothing configures
it.

**Write every identifier in the form the tools take.** The window is the agent's only route to
the entities it names, so a short label there costs turns. A hook that rendered a feeding job as
`__deployment__.ingest_reporting` cost a five-turn run two of its turns: turn 1 on two
`job not found` errors, turn 2 on a `dlthub_list_jobs` probe to recover the `jobs.` prefix.
Writing `jobs.__deployment__.ingest_reporting` into the same evidence finished the task in four
turns with no other change. A job tool takes the full `jobs.<section>.<name>` ref or the job's
uuid, a run tool takes the run uuid, and the hook already holds both, so render what the tool
accepts.

The hook is also the cheaper run. The counts arrive in the system prompt instead of costing a
turn each, and a column the warehouse does not have is reported in the window, so the agent puts
it in its open points rather than guessing around it.

A decorated function owns its own run, so neither `agent.py` nor the `inputs_validator` and
`outputs_validator` arguments of `run.agent` reach it. It calls the same functions itself, around
`loop.run`.

## Code around the loop

The declared form leaves no place for code that has to run before the loop and again after it.
Decorate a function with `run.agent(agent="<toolkit>:<agent>")` instead. The function owns the run
and keeps the referenced definition's prompt and schemas.

```python
import sys
from typing import Annotated

from dlt.hub import run

sys.path.insert(0, ".claude/dlthub/agents/<toolkit>/<agent>")
from helpers import after, before


@run.agent(
    agent="<toolkit>:<agent>",
    trigger="schedule:0 7 * * *",
    require={"profile": "access"},
)
async def wrapped_agent(
    run_context: run.TJobRunContext = None,
    target_run_id: Annotated[
        str,
        run.Entity("job-run"),
        run.Doc("run id to work on; empty on a trigger"),
    ] = "",
) -> dict:
    prep = before(run_context, target_run_id=target_run_id)
    if prep.aborted:
        # this path never started the loop, so a returned dict fails on `loop.trace`
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

Raise `JobAbortedException` on any path that did not complete a loop run. dltHub reads `loop.trace`
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

Code that talks to the platform reads dltHub's own `active().runtime_config` for the credential
(`api_key` or `auth_token`, `workspace_id`, `api_base_url`) rather than the environment. The same
call resolves from `.dlt/config.toml` locally and from the mounted configuration on the runner, so
the same code runs in both places.

The JWT that `dlthub login` writes expires after about an hour, so a fetcher passes a credentials
object the SDK renews through. A static token makes a long run fail halfway with `token_expired`.

## Triggers that would loop

Do not point an agent that reacts to a failure at `job.fail:*` in a workspace where another
agent job can fail. The selector expands onto every other job, so a failure there is inspected,
the inspection fails in turn and starts the first agent again. Name the jobs, or tag them. A tag
that matches no job is reported at deploy time as `matched no job`.

Two mechanisms narrow a broad selector. The agent aborts when the run it resolved belongs to its
own job, and a job event never fires on a manual run. Name the jobs anyway: dltHub has no manifest
validation for this yet, because a selector is expanded to concrete refs at deploy time and
nothing compares the result against the jobs that run agents.

## Pinning the model

An agent definition doesn't name a model, so the workspace sets it. The runtime doesn't supply
one either: a workspace with no variables set falls back to the loop's default alias and the run
fails on the first model call with the provider's own missing-key error, before a turn is taken.
`agent.model`, `agent.api_key`, `agent.api_url` and `agent.api_version` are one set: a run takes
all four from the workspace or all four from the runtime. Setting `api_key` alone leaves `model` unset, so the run sends the
agent's default model to your endpoint and gets `401 API key is invalid`. Set them as workspace
variables, which arrive on the runner as environment and override `.dlt/secrets.toml`:

```bash
printf '%s' '<key>' | dlthub variable set AGENT__API_KEY --secret --workspace
```

```bash
printf '%s' 'anthropic:claude-sonnet-5' | dlthub variable set AGENT__MODEL --plain --workspace
```

Every `variable set` takes `--plain` or `--secret`, and it writes to the workspace the current
directory is connected to. Check with `dlthub variable list` that the value landed where the job
runs.

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

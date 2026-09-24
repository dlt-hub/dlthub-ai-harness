# Background agents

A **background agent** is a toolkit item alongside skills, commands and rules. Where a skill
is a procedure a coding assistant follows with a person watching, a background agent runs
unattended: on a schedule, after a job fails, or when someone starts it from the web UI or
the command line.

This document is a guideline for authors of background agents. An agent is an `AGENT.md`,
written much like a `SKILL.md`, and the working example is
[`job-inspector`](workbench/dlthub-platform/agents/job-inspector/AGENT.md).

## Definition of terms

- **agent definition**: what the `AGENT.md` declares. The system prompt, the inputs and
  output, the tools, skills and rules the agent uses, and the access it needs. A toolkit ships
  definitions. (pydantic-ai, the AI harness the dltHub background agents are built on,
  calls this an `AgentSpec`.)
- **agent job**: a definition plus the settings that say how it operates in one workspace:
  model, token and turn limits, trigger, instructions, loop. A workspace declares it with
  `run.agent("<toolkit>:<name>", ...)`. (This is what pydantic-ai and claude-agent-sdk call an
  Agent, and what the dltHub web UI lists as one.)
- **agent run**: an execution of the agent job. It takes inputs (for example a job run id)
  and returns the agent output and a trace. Instructions, limits and model can be overridden
  for a single run through job configuration.
- **agent loop**: the framework that runs the model turn by turn. Two are built in:
  `pydantic-ai`, the default, and `claude-agent-sdk`, which runs Claude Code and accepts
  Anthropic models only. A job selects one with `loop=` on `run.agent` or `agent.loop` in
  config.

Everything below is about the first of these, the agent definition: writing it so that any
job built on it, and any run of that job, follows your instructions.

## Where it lives, where it installs

```
workbench/<toolkit>/agents/<name>/AGENT.md
```

A folder, like a skill, so a definition can grow supporting files. `dlthub ai toolkit
install <toolkit>` copies it to `.claude/dlthub/agents/<name>/` (`.cursor/dlthub/agents/`,
`.agents/dlthub/agents/` on the other hosts). It lands under `dlthub/` there because the
hosts scan their own folders for native subagents (`.claude/agents/`, `.codex/agents/`) and
a dltHub agent is not one. A workspace refers to it as
`<toolkit>:<name>`. The workspace's toolkit index (`.dlt/.toolkits`) travels with every
deployment, so the reference resolves on the runner as it does locally. Everything that runs
it lives in dlt; the toolkit ships only the file.

## Anatomy of `AGENT.md`

YAML frontmatter, then a markdown body. **The frontmatter declares; the body is the system
prompt.** Only the body is required: a file with no frontmatter is a valid definition, named
after its folder, with the standard output and nothing else.

| field | meaning |
|---|---|
| `name` | the folder name; state it only to have it in the file |
| `description` | what the agent does and when to run it; shown in the UI |
| `tools` | feature groups of the dlthub MCP server the agent gets, and nothing else (§ tools) |
| `skills`, `rules` | `<toolkit>:<name>` refs to components the agent uses (§ skills and rules) |
| `access` | what the agent may touch: `local`, `data`, `context` (§ access) |
| `inputs` | JSON Schema of what the agent takes; every input is a job configuration key (§ inputs) |
| `output` | JSON Schema of what the agent returns; `status` and `summary` are always in it (§ output) |
| `defaults` | settings the agent job and the run may override: `trigger`, `model`, `limits`, `loop_run_args` (§ defaults) |
| body | the system prompt, a template over `inputs` (§ the body) |

### `tools`

Feature groups of the dlthub MCP server, the platform-side tools: `jobs`, `logs`,
`telemetry`, `workspace`, `pipeline`, `toolkit`, `secrets`, `context`, plus whatever other
plugins contribute. The agent gets exactly the groups listed, not the server's interactive
defaults, and within a group only the tools its `access` covers (§ access). No `tools`, no
server.

```yaml
tools: [jobs, logs, telemetry]
```

### `skills` and `rules`

References to components of the same toolkit or one of its declared dependencies, as
`<toolkit>:<name>`. Skills are what the agent may invoke. How they reach the model depends
on the loop: pydantic-ai inlines their text into the system prompt, claude-agent-sdk lists
them by name and loads them on demand. Rules are inlined into the system prompt on every
loop. Only the listed components reach the agent; nothing else installed in the workspace
does. A reference that does not resolve is skipped with a warning, and the agent runs with
less.

```yaml
skills: [dlthub-platform:debug-deployment]
rules: [init:dlthub-workspace, dlthub-platform:job-resources]
```

### `access`

What the agent may touch, per axis, as one verb or a list. Declaring nothing wires nothing:
no file tool, no shell, and an MCP server that serves only the toolkit catalogue.

```yaml
access:
  local: [read, execute]    # read | write | execute | network | all
  data: [read]              # read | write | all
  context: [read]           # read
```

| axis | verbs | what it buys |
|---|---|---|
| `local` | `read` | `Read`, `Glob`, `Grep`: the workspace files |
| | `write` | `Write`, `Edit` on the pydantic-ai loop; `Write`, `Edit`, `MultiEdit`, `NotebookEdit` on the claude-agent-sdk loop |
| | `execute` | `Bash` (`PowerShell` on Windows), `RunPython`, in the workspace, in the job's own process tree |
| | `network` | `WebFetch`, `WebSearch` |
| `data` | `read`, `write` | workspace data through the MCP server's data tools. `read` offers the read tools only and restricts SQL to `SELECT`. Mapping the verb to a dlt profile is planned |
| `context` | `read` | runs, logs, job definitions and telemetry through the MCP server. The only verb served; `write`, `execute` and `deploy` are refused at manifest time until a runtime serves them |

The agents this repo ships do not grant `data`. A background diagnosis is built from run
records, logs, job definitions and telemetry, not destination rows. A `data` grant exposes
workspace data to a model-driven process and is outside the job-inspector/evaluator safety
model.

`local` verbs are named after Claude Code's tools, so one declaration means one thing on
both loops, pydantic-ai and claude-agent-sdk. The set each verb wires differs: the
claude-agent-sdk loop adds the CLI tools that extend a name, `MultiEdit` and `NotebookEdit`
under `Edit`, `NotebookRead` under `Read`, `BashOutput` and `KillShell` under `Bash`, and it
has no `RunPython`, so Python runs through the shell. Credential files (`*secrets.toml`,
`.env`) are never readable, whatever `local` says. MCP tools declare what they require, and
a tool the declaration does not cover is not offered to the model. The declaration is a
request: the runtime grants what it can, and the trace of every run lists the tools that
were wired.

Write the policy the declaration enforces into the body as explanation: "you are read-only"
in the prompt helps the model understand its role; the `access` block is what makes it so
for the MCP tools. `local: execute` is the exception: the shell runs under the job's
credentials and nothing gates what it does with them, so an agent with `execute` and data
access needs an explicit rule in the body never to write data.

### `inputs`

A JSON Schema. Every property is a job configuration key: `dlthub local run <job> -c
failed_run_id=...`, `jobs.<section>.<job>.failed_run_id` in `config.toml` or the
environment, or a run argument the trigger carries. The body refers to inputs as
`{{ name }}` and to the run itself as `{{ run_context.trigger }}`, `{{ run_context.run_id }}`,
`{{ run_context.refresh }}` and, on a job with an interval, `{{ run_context.interval_start }}`
and `{{ run_context.interval_end }}`; `run_context` is implicit and never declared.

```yaml
inputs:
  type: object
  properties:
    failed_run_id:
      type: string
      description: run id of the failed job run to inspect
      entity_type: job-run
  required: {}
```

- A required input with no value fails the run like any missing job argument. An optional
  one nobody supplied renders as empty text, so **the body must say what to do with partial
  input**: which combinations are workable, and when to abort.
- `required: {}` is how "nothing required" is written; `[]` works too.
- An input the body never names is a warning at manifest time: nothing would read it.
- There is no `inputs.prompt`. The task is the body.

### Entities: `entity_type`

An input that names a workspace entity carries `entity_type`: `job-run`, `job`, `pipeline`,
`dataset` or `workspace`. The agent receives the bare id (a run id, a job ref, a pipeline
name); dlt composes the entity reference `job-run/<id>` when it reports.

Declaring it does two things:

1. The run reports the entity in its job result's `object` list, so the run shows up on
   that entity's page.
2. The **first** entity-typed input becomes `expose.object_input` in the deployment
   manifest, `{entity_type, input}`. That is how the web UI offers the agent job from an
   entity, a failed run's row for job-inspector, and knows which key to pass the entity under.

Declare the same name with `entity_type` on an **output** property when the agent may end
up acting on a different entity than it was given: an output overwrites the input of the same
name in `object`, so an inspector that resolved a run from a job ref reports the run it
actually inspected.

### `output`

A JSON Schema of the agent output. Two properties are the contract every agent shares and
dlt adds them, with their descriptions, when a definition leaves them out:

```yaml
output:
  type: object
  properties:
    status:
      enum: [succeeded, failed, aborted]
      description: >
        Outcome of your task. `succeeded` and `failed` mean what your system prompt says
        they mean. `aborted`: you hit something that prevents doing the task at all, and
        the runner raises an exception carrying `summary`.
    summary:
      type: string
      description: Markdown. What you accomplished. When `status` is `aborted` this becomes the exception text, so say what blocked you.
  required: [status, summary]
```

Declare them anyway: the file then shows the whole contract, and `make validate-toolkits`
checks they carry the standard values. A declaration that contradicts them (`status` with
other values, `summary` not a string) fails validation, because dlt would overwrite it and
lose your intent. A domain outcome gets its own name: a data-quality agent returns
`verdict`, not a second `status`.

Add the agent's own fields next to them. Three things to know:

- **The model sees the whole schema, descriptions and enums included.** A description is
  the only place semantics travel; an enum says which values are legal, not when to pick
  which. Describe every field whose name does not say it all.
- **Constrained decoding guarantees shape, not truth.** A misread field is a confident,
  schema-valid, wrong answer. The body has to define what each value means (§ the body).
- **The schema reaches the model as declared.** dlt changes one thing: `entity_type` moves
  into `$comment`, because strict validators reject keywords they do not know. Nothing is
  added or relaxed on your behalf, so write what the provider accepts. For example,
  Anthropic's structured output rejects `minimum`, `maximum` and `minLength`. Put numeric
  bounds in the description.

The agent run's `status` decides what the job does: `succeeded` and `failed` complete the
run; `aborted` raises with `summary` as the message and the run fails, after the result and
trace were delivered.

### `defaults`

Settings the agent job may set differently and a run may override again:

```yaml
defaults:
  trigger: [job.fail:*]                 # trigger strings, selectors allowed
  model: sonnet                         # alias, or provider:model
  limits: {max_turns: 30, max_tokens: 1000000}
  loop_run_args: {retries: 1}           # framework-specific; unknown keys are reported, not fatal
```

`trigger` takes dlt trigger strings: `schedule:0 7 * * *`, `job.fail:<job ref or selector>`,
`job.success:...`; `job.fail:*` watches every job in the workspace and expands at manifest
time, never onto the job that declares it. A job event never stands in for a manual run: a
run started by hand or from the UI arrives with a `manual:` trigger and only the inputs it was
given, which is one more reason the body must say what to do with empty input. `model` is an
alias (`sonnet`, `opus`, `haiku`, `fable`, `gpt`, `gpt-mini`, `gpt-nano`, `gemini`,
`gemini-pro`) or a `provider:model` id. `limits.max_tokens` is counted by dlt after every
turn, so it means the same on every loop. `loop_run_args` are handed to the framework:
`retries` is how often pydantic-ai lets the model correct a failing tool call; keys a loop does
not know are listed in the trace as ignored.

Precedence, lowest first: loop default, `defaults` here, the agent job's arguments,
configuration at run time. A runtime value always wins, so put here what should hold when
nobody says otherwise, and nothing that must hold.

## The body

The body is the system prompt: who the agent is, what it produces, what "done" means, and
the task itself with its inputs named. It is a template: `{{ name }}` and `{{ a.b }}` are
substituted before the first turn, and that is the whole grammar. Write it as you would a
skill, for a reader that has the tools and none of the context.

What the model gets besides the body: the rules inlined, the skills listed or inlined, a
sentence naming the workspace folder and the temp folder for scratch files, the output schema
with its descriptions, and the tools `access` and `tools` bought. On
claude-agent-sdk the workspace's `CLAUDE.md` loads as in any Claude Code session, while the
`.claude/rules` folder stays out. What it gets as the user turn is the agent job's
`instructions`, or a bare "Go ahead". Do not restate any of that.

Six things a body should do, with job-inspector as the example:

1. **State the role in two sentences, including the unattended setting.** "You run
   unattended, seconds after a job failed. An engineer reads your output only when the
   failure matters, so it must stand on its own."
2. **Define `succeeded`, `failed` and `aborted` for this agent.** The schema deliberately
   does not. Write the bar as a positive claim and name the failure mode you fear; with
   constrained decoding the cheap escape from `failed` is a guess dressed as success.
   "The distinction that matters is cause found versus cause not found, not whether the
   problem got solved."
3. **Say what to do with each input, and with its absence.** Inputs are usually optional.
   Name the fallbacks in order, and the point at which nothing is left to work on and the
   answer is `aborted`.
4. **Give the first steps concretely.** Which tool or command to run first, what to read,
   what the tell-tale signs are. A skill reference is good here; a skill the agent has is
   loaded on demand.
5. **List constraints as rules, not adjectives.** "Never edit code, never deploy, never
   re-run a job" beats "be careful".
6. **Define every enum the output declares.** A table of value and when it applies. Say what
   `unknown` or `low` means and that reporting it is a legitimate outcome.

Keep the body under about two hundred lines. The rules and skills it references carry the
platform knowledge; the body carries the judgement.

## From the definition to a job and a run

A workspace turns the definition into an agent job in its deployment module:

```python
from dlt.hub import run

inspector = run.agent(
    "dlthub-platform:job-inspector",
    trigger="job.fail:tag:ingest",       # narrower than the default
    model="opus",
    require={"profile": "access"},       # see "Profile"
    instructions="focus on the loader step",
)
```

Every decorator argument overrides the matching `defaults`; `instructions` is the user turn
of every run. The job is named after the definition (`job_inspector`). Instead of a
`<toolkit>:<name>` reference the workspace may point at a folder holding an `AGENT.md` by its
workspace-relative path. A function decorated with `run.agent` can also be a definition on its
own, or drive an installed one; see the dlt documentation for that form.

### Profile

**An agent job never runs on `prod`.** Pin the read-only profile on every one of them:

```python
require={"profile": "access"}
```

Without this pin, an agent job is a batch job on `prod` and gets production credentials in
its environment. Declare the profile alongside the `access` block: `access` decides which
tools the model is offered; the profile decides which credentials the job process holds.

The pin governs profile-scoped credentials: `prod.secrets.toml`, `prod.config.toml`, and a
variable set with `dlthub variable set --profile prod`. A variable set with `--workspace`
has no profile and reaches the job whatever it runs on, so a secret that must stay away from
an agent belongs in a profile scope rather than the workspace scope. `dlthub variable list`
prints the scope of each one in its `Profile` column.

Work that needs production write credentials belongs in a pipeline or a plain job, which a
person wrote and reviewed, and an agent proposes it rather than performing it.

Nothing at deploy time enforces this. Manifest validation rejects a local-only profile
(`dev`, `tests`) and otherwise takes the name as given: `prod` passes, and so does a typo
like `acess`, which then surfaces as missing credentials at run time. The rule holds because
authors apply it, and `job-inspector-eval` catches a break after the fact with the
`agent_profile_not_prod` check, which reads the profile off the run record.

The profile has to be `configured` in the workspace; workspace info lists which ones are. On
`dlthub local run` the declaration is a warning rather than a switch: the run uses the active
profile and reports the mismatch, so check the active profile before running an agent job by
hand.

A run happens when the trigger fires, or by hand:

```bash
dlthub local run job_inspector -c failed_run_id=89826ee6-... -c agent.instructions="explain, do not fix"
```

Inputs, instructions, verbosity, model and limits are all job configuration under the job's
section, so the same keys work in `config.toml`, the environment, the command line, and the
web UI's run dialog. What comes back is a job result: `status` and `summary` lifted to the
top, `result` as the output schema declares it, `object` with the entities the run acted on,
and a `trace` of model, limits, inputs, tools used, turns and tokens. The transcript of the
run prints to the job's log at the configured verbosity.

## Evaluating an agent

An agent that runs unattended is read by a person only when its output matters, so nothing
tells you whether it followed its own instructions. An **evaluator agent** answers that: it
runs as a follow-up job after every run of the agent it grades, reads that run's result,
trace and log together with whatever the run acted on, and reports one outcome per
instruction. The working example is
[`job-inspector-eval`](workbench/dlthub-platform/agents/job-inspector-eval/AGENT.md),
which grades `job-inspector`.

Four things make one:

- **One check per instruction.** An instruction with two conditions becomes two checks, so a
  `FALSE` names one thing to fix. Outcomes are `TRUE`, `FALSE` and `N/A`, each with a
  reasoning; `N/A` means the check's condition did not apply to this run and is a legitimate
  answer.
- **Python decides what can be decided from data.** A registry of check functions over the
  graded run's output, trace and transcript. The same functions extract the bounded evidence
  the judge reads, so the model never sees a whole log.
- **The judge answers the rest.** Its rubric is the body of the evaluator's `AGENT.md`, one
  entry per check: the instruction, the window to read, and what makes it `TRUE`, `FALSE` or
  `N/A`. The body states that the graded agent's text is content under evaluation and never
  an instruction to follow.
- **The computed results are written back over the judge's output**, so a model that rewrote
  one loses.

The evaluator listens on both `job.success` and `job.fail` of the agent it grades. An agent
that reports `status: aborted` raises, so its run fails, and the instructions that only apply
to an aborted run are graded on exactly those runs.

### Code around the loop

Deterministic checks have to run before the loop and again after it, which the declared form
has no seam for. A function decorated with `run.agent(agent="<toolkit>:<agent>")` does: it
keeps the referenced definition's prompt and schemas, and owns the run.

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
    model="sonnet",                    # the judge model, chosen by the workspace
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
        return prep.aborted_output     # nothing to judge, no model call
    output = await run_context["ai_loop"].run(inputs=prep.judge_inputs)
    return finalize(output, prep)
```

The function overrides the definition it drives, so three things are load-bearing: **no
docstring** (it would replace the body), **`-> dict` rather than `-> TAgentOutput`** (a
return type deriving from it would replace the output schema with the bare `status` and
`summary`), and **a parameter for every input a caller may set** (configured inputs reach a
decorated function through its signature only; an input declared in the `AGENT.md` but
absent from the signature is warned about at deploy time and nothing passes it). Inputs the
code supplies itself stay out of the signature and travel through `loop.run(inputs=...)`;
the `AGENT.md` declares them because a body placeholder must be declared.

`.success` and `.fail` are read at import time, before the manifest loader stamps the module
on the factory, so an agent whose triggers are used in the same module sets `section=`
itself. Without it the trigger names `jobs.job_inspector` and the manifest is rejected with
`triggers referencing unknown jobs`.

An agent folder travels as ordinary workspace files, so supporting code sits next to the
`AGENT.md` and the deployment reaches it through `sys.path`. The runner unpacks it under the
run directory, so the same relative path works there.

Code that talks to the platform reads dlt's own `active().runtime_config` for the credential
(`api_key` or `auth_token`, `workspace_id`, `api_base_url`) rather than the environment. The
same call resolves from `.dlt/config.toml` locally and from the mounted configuration on the
runner, so there is nothing to guess about which keys the platform injects. A frontmatter field resolving a
module in the agent folder would replace that line; it is a dlt follow-up.

## Validation

`make validate-toolkits` checks every `agents/<name>/AGENT.md` in the workbench:

- frontmatter, if present, is valid YAML, and a stated `name` matches the folder
- the body is not empty, and every `{{ placeholder }}` in it is declared under
  `inputs.properties` or reachable under `run_context`
- `access` axes and verbs are known
- no `inputs.prompt`
- `output` declares `status` and `summary`, described and required, with the standard
  values; a contradicting declaration is an error, a missing one a warning
- `skills` and `rules` refs resolve in the toolkit or a declared dependency
- `defaults` and `defaults.limits` keys are known

dlthub validates again when the deployment manifest is generated: the body is required, the
name falls back to the folder, `access` is checked, an unknown `entity_type` is refused, a
`prompt` input is refused, an input the body never mentions is a warning, and a skill or rule
that does not resolve in the workspace is skipped with a warning.

## Authoring checklist

- The folder name is the agent's name; `description` says when to run it.
- `tools` lists only the feature groups the task needs; `access` only the verbs it needs.
- Every input has a `description`, entity inputs have `entity_type`, and the body names every
  input and says what to do when it is empty.
- `output` keeps `status` and `summary` as declared above and describes every field of its
  own; an entity the agent may resolve itself is an output property too.
- The body defines succeeded, failed and aborted for this agent, gives the first steps, and
  defines every enum.
- `defaults` holds a sensible trigger, model and limits; nothing in it is a requirement.
- `make validate-toolkits` passes.

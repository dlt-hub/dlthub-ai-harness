# Background agents

A **background agent** is a toolkit item alongside skills, commands and rules. It runs
unattended: on a schedule, after a job fails, or when someone starts it from the web UI or
the command line.

This document is a guideline for authors. An agent is an `AGENT.md`, written much like a
`SKILL.md`; the working example is
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
  config. `claude-agent-sdk` is not officially supported: the agents in this repo are written
  for and tested on `pydantic-ai`, and what the other loop does is recorded here as
  observation rather than as a contract.

Everything below is about the first of these, the agent definition: writing it so that any
job built on it, and any run of that job, follows your instructions.

## Where it lives, where it installs

```
workbench/<toolkit>/agents/<name>/AGENT.md
```

A folder, like a skill, so a definition can grow supporting files. `dlthub ai toolkit
install <toolkit>` copies it to `.claude/dlthub/agents/<name>/` (`.cursor/dlthub/agents/`,
`.agents/dlthub/agents/` on the other hosts). It lands under `dlthub/` because the hosts scan
their own folders for native subagents (`.claude/agents/`, `.codex/agents/`), which a dltHub
agent is not. A workspace refers to it as `<toolkit>:<name>`. The workspace's toolkit index
(`.dlt/.toolkits`) travels with every deployment, so the reference resolves on the runner as
it does locally. The toolkit ships the file and dlt runs it.

## Anatomy of `AGENT.md`

YAML frontmatter, then a markdown body. **The frontmatter declares what the agent has, and
the body is its system prompt.** Only the body is required: a file with no frontmatter is a
valid definition, named after its folder, with the standard output.

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

What the agent may touch, per axis, as one verb or a list. An empty block wires no file
tool, no shell, and an MCP server serving the toolkit catalogue alone.

```yaml
access:
  local: [read, execute]    # read | write | execute | network | all
  data: [read]              # read | write | all
  context: [read]           # read
```

| axis | verbs | what it wires |
|---|---|---|
| `local` | `read` | `Read`, `Glob`, `Grep`: the workspace files |
| | `write` | `Write`, `Edit`, and whatever else the loop wires under those names |
| | `execute` | `Bash` (`PowerShell` on Windows), `RunPython`, in the workspace, in the job's own process tree |
| | `network` | `WebFetch`, `WebSearch` |
| `data` | `read`, `write` | workspace data through the MCP server's data tools. `read` offers the read tools only and restricts SQL to `SELECT`. Mapping the verb to a dlt profile is planned |
| `context` | `read` | runs, logs, job definitions and telemetry through the MCP server. The only verb served; `write`, `execute` and `deploy` are refused at manifest time until a runtime serves them |

`job-inspector` grants `local: read` and `context: read`: it investigates an open question
and cannot know in advance which file or which record answers it. `job-inspector-eval` grants
nothing and declares no `tools`: it answers a fixed list of checks, so its preparation step
fetches every artifact those checks read before the loop starts and hands the judge bounded
windows.

Neither `job-inspector` nor `job-inspector-eval` grants `data`. Both work from run records,
logs, job definitions, telemetry and source, and a `data` grant would put workspace data in
front of a model-driven process.

Credential files (`*secrets.toml`, `.env`) are never readable, whatever `local` says. A tool
the declaration does not cover is not offered to the model, and the trace of every run lists
the tools that were wired.

Repeat the policy in the body as explanation: "you are read-only" helps the model understand
its role, and the `access` block enforces it for the MCP tools. `local: execute` is the
exception: the shell runs under the job's credentials and nothing gates what it does with
them, so an agent with `execute` and data access needs an explicit rule in the body never to
write data.

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

Add the agent's own fields next to them. What to know about the schema:

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
- **Every object names its `properties`.** A bare `type: object` means "any object", which a
  strict validator refuses, so OpenAI's structured output falls back or rejects the schema. A
  field Python fills after the loop is declared as fully as one the model writes.
- **Keep the schema small.** The model reads all of it on every run, and a large one has
  stopped a job launching. `job-inspector-eval` declares 17 properties in about 5,600
  characters, and a test holds it under 7,800.

The agent run's `status` decides what the job does: `succeeded` and `failed` complete the
run; `aborted` raises with `summary` as the message and the run fails, after the result and
trace were delivered.

#### The shape of `summary`

The platform renders `summary` as markdown on the run page, and it is the only field a
reader sees without opening the result. Every agent writes it the same way:

- **Markdown headings over short bullets, and nothing else.** No text before the first
  heading, no text outside a bullet, no question or bracketed note next to a heading.
- **The same headings on every run of one agent**, in the same order, named for what that
  agent reports. Take the default for the kind of agent below and change it where the agent
  reports something else. Declare the set in the body and hold to it.
- **The finding comes first and the scope last.** The first section says what the run found;
  what it covered goes at the bottom, next to the detail a reader opens from there.
- **One or two plain sentences per bullet, one fact each.** Two verbs joined by `and` or
  `then` are two bullets.
- **A part of a finding is a bullet under it, nested one level.** A grade's categories and a
  check's broken instructions sit inside the finding they belong to. Only `##` headings, so
  every heading is a section a reader can scan for.
- **What the run could not cover goes in `Scope`.** Checks that did not apply, inputs that
  could not be read, a window that was cut short. An agent with no `Scope` section puts them
  in its last section, which is what `job-inspector` does with `Confidence`.
- **A markdown table only as the last thing in the last section**, when the agent reports
  rows. Its headers are lowercase and name the field in the row. A row that measured nothing
  stays out; how many there were belongs in `Scope` or in the tally above the table.
- **Every run id and job ref is a link**, wherever it falls.
  `[`<id>`](<web ui base>/w/<workspace id>/runs/<id>)` for a run, `/jobs/<job ref>` for a job.
  `dlt_runtime.urls` builds that base from the API base url, which is how the CLI prints a run
  link.
- **Markdown only, no raw HTML.** The summary renderer in the web UI strips tags, so a
  `<details>` element folding a long list arrives as an empty section. A long list goes in as
  plain bullets.
- **Close every code span, and never escape a backtick with a backslash.** An unbalanced span
  swallows the rest of the line in the UI, and `\`` renders as itself.
- **No verdict label at the top.** State what was found; `passed` and the other output fields
  carry the verdict.

State the shape in the body and check it. `job-inspector` has the rules under "Summary
format", and `job-inspector-eval` grades them with `summary_has_required_sections`,
`summary_sections_are_bullets`, `summary_code_spans_balanced` and `summary_within_length`. An
agent that assembles its summary in Python around the loop splits what the model wrote into
bullets itself.

##### Default sections

An agent that investigates, inspects or analyses an entity in the workspace takes the
sections `job-inspector` writes:

| heading | the bullets answer |
|---|---|
| `## Diagnosis` | What happened, where, and why; the bullet that carries the cause quotes its evidence with the source and the line |
| `## Recommendation` | What the reader does next: the target and the change, written as the instruction itself |
| `## Confidence` | What this rests on and what it leaves open; when nothing was left open, one bullet says so |

An agent that grades another agent's run takes the sections `job-inspector-eval` writes,
which open on the verdict and keep the evidence underneath:

| heading | the bullets answer |
|---|---|
| `## Findings` | The counts, any rule broken that outranks the rest, what the graded agent got wrong and why it matters, then one bullet per category with its verdict and every broken check nested under it |
| `## Recommendation` | What to change in the graded agent's definition so a broken check stops recurring. A report over one run leaves this out, because a change to an agent's instructions rests on a pattern across runs |
| `## Scope` | How many checks did not apply, then the run or runs graded and what each acted on, each linked |
| `## Detailed evaluation results` | The tally, then the table of every decided check: `check_id`, `category`, `kind`, `results`, `reasoning` |

`job-inspector-eval` names its two categories `Instruction following` and `Quality`; a grader
with other categories renames those bullets and leaves the rest. A report over many runs takes
the same sections, with the window, the runs skipped and the reasons under `Scope`, and each
broken instruction states the runs it broke on.

Changing a section the evaluator grades means changing the evaluator too:
`REQUIRED_SUMMARY_SECTIONS` in `checks.py` holds the inspector's three headings, and the
checks that read the `Confidence` section by name go with them.

### `defaults`

Settings the agent job may set differently and a run may override again:

```yaml
defaults:
  trigger: [job.fail:*]                 # trigger strings, selectors allowed
  limits: {max_turns: 30, max_tokens: 1000000}
  loop_run_args: {retries: 1}           # framework-specific; unknown keys are reported, not fatal
```

`trigger` takes dlt trigger strings: `schedule:0 7 * * *`, `job.fail:<job ref or selector>`,
`job.success:...`. `job.fail:*` watches every job in the workspace and expands at manifest
time, never onto the job that declares it; see "Triggers that would loop" before using it. A
run started by hand or from the UI arrives with a `manual:` trigger and only the inputs it
was given, which is why the body must say what to do with empty input. `limits.max_tokens` is
counted by dlt after every turn, so it means the same on every loop. `loop_run_args` are
handed to the framework: `retries` is how often pydantic-ai lets the model correct a failing
tool call, and keys a loop does not know are listed in the trace as ignored.

Precedence, lowest first: loop default, `defaults` here, the agent job's arguments,
configuration at run time. A runtime value always wins, so put here what should hold when
nobody says otherwise, and nothing that must hold.

### The model

`model` is an alias (`sonnet`, `opus`, `haiku`, `fable`, `gpt`, `gpt-mini`, `gpt-nano`,
`gemini`, `gemini-pro`) or a `provider:model` id. The workspace deploying the agent sets it
in one place, the `AGENT__MODEL` variable, which every agent job in that workspace reads.
`run.agent` also takes `model=`, and configuration outranks it, so a value in the deployment
code is silently beaten by the variable; leave it out and the two cannot disagree.

A definition shipped in a workbench toolkit names no model. An alias resolves on Anthropic,
OpenAI and Google; an Azure workspace addresses a deployment on its own endpoint and has no
alias, so a shipped `model: sonnet` is a default it cannot resolve. `make validate-toolkits`
rejects one.

Say in the `AGENT.md` what to pin instead: the class of model the instructions were written
for, as "at least as capable as Claude Sonnet 5".

`loop: claude-agent-sdk` is the same decision by another name, since it takes Anthropic
models only. Leave it to the workspace: that loop is not officially supported, and an agent
pinned to it runs on one provider.

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

What a body should do, with job-inspector as the example:

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

Keep the body under about two hundred lines. The rules and skills it references hold the
platform knowledge, so the body holds what this agent has to decide.

## From the definition to a job and a run

A workspace turns the definition into an agent job in its deployment module:

```python
from dlt.hub import run

inspector = run.agent(
    "dlthub-platform:job-inspector",
    # access comes from the definition: local: [read], context: [read]. an `access=`
    # argument on a referenced agent is dropped; see below
    # `ingest` is a tag this workspace puts on its own jobs, narrower than the default
    trigger="job.fail:tag:ingest",
    require={"profile": "access"},       # see "Profile"
    instructions="focus on the loader step",
)
```

Every decorator argument overrides the matching `defaults`, and configuration overrides both;
`instructions` is the user turn of every run. The job is named after the definition (`job_inspector`). Instead of a
`<toolkit>:<name>` reference the workspace may point at a folder holding an `AGENT.md` by its
workspace-relative path. A function decorated with `run.agent` can also be a definition on its
own, or drive an installed one; see the dlt documentation for that form.

`access`, `tools`, `skills` and `rules` are not defaults. A referenced agent keeps the
definition's lists and the decorator drops its arguments for them. A decorated function
driving a referenced agent replaces the definition's list with the argument, so
`access={"local": ["read"]}` on such a function removes `context: read`. Pass every axis the
agent needs, or leave the block to the definition.

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

An evaluator has four parts:

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
- **The computed results are written back over the judge's output**, so a judge answer that
  contradicts a computed one is discarded.

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
from checks import DEFAULT_MAX_RUNS_READ, judge_runs, prepare

# `section` is explicit because `.success` and `.fail` are read at import time, before the
# manifest loader stamps the module; without it the trigger names `jobs.job_inspector`
inspector = run.agent(
    "dlthub-platform:job-inspector",
    section="__deployment__",
    trigger="job.fail:tag:ingest",
    require={"profile": "access"},
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
    evaluations, degraded = await judge_runs(
        run_context["ai_loop"], [prep], tolerate_failures=True
    )
    if not evaluations:
        # the judge ran out of turns or tokens after Python decided its checks; `judge_runs`
        # kept those rather than lose the run's whole result
        raise run.JobAbortedException(degraded[0]["summary"], degraded[0])
    return evaluations[0]
```

The function overrides the definition it drives, so watch the signature. Give it **no
docstring**, since a docstring replaces the body. Return **`dict` rather than
`TAgentOutput`**, since a return type deriving from `TAgentOutput` replaces the output
schema with the bare `status` and `summary`. Take **a parameter for every input a caller may
set**, since configured inputs reach a decorated function through its signature only, and an
input declared in the `AGENT.md` but absent from the signature is warned about at deploy
time and nothing passes it. Inputs the code supplies itself stay out of the signature and
travel through `loop.run(inputs=...)`; the `AGENT.md` declares them because a body
placeholder must be declared.

A path that never started the loop raises rather than returns. dlt reads `loop.trace` on any
returned dict carrying `status`, so returning one from the abort branch fails the run with
`AgentTraceNotAvailable` and loses the abort reason. A loop that started and then raised is
the same case: it records its trace only on the way out of a normal return, so the degraded
evaluation goes out through `JobAbortedException` too.

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

### Running an evaluator on a schedule

The declaration above evaluates one run per trigger. A workspace that would rather read one
report covering the runs of the current definition deploys the same agent on a schedule and
lets the preparation step resolve the window:

```python
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
    window_days: Annotated[int, run.Doc("fallback window with no deployment history")] = 7,
    max_runs: Annotated[int, run.Doc("runs one scheduled job evaluates")] = 25,
) -> dict:
    batch = prepare_batch(run_context, inspector_job_ref=inspector_job_ref,
                          window_days=window_days, max_runs=max_runs)
    if batch.aborted:
        raise run.JobAbortedException(batch.abort_reason, batch.aborted_output)
    # one run out of budget or out of shape must not cost the rest of the window
    evaluations, degraded = await judge_runs(
        run_context["ai_loop"], batch.preps, tolerate_failures=True
    )
    if not evaluations:
        # not one loop run completed, so `loop.trace` does not exist and a returned dict
        # fails the job on it; the degraded runs carry their deterministic checks into the
        # aborted output
        report = finalize_batch([], batch, degraded)
        if batch.found:
            raise run.JobAbortedException(report["summary"], {**report, "status": "aborted"})
        print(report["summary"])
        return {}
    recommendation = await judge_window_recommendation(
        run_context["ai_loop"], evaluations + degraded, batch
    )
    return finalize_batch(evaluations, batch, degraded, recommendation)
```

What the scheduled path settles:

- **The window starts at the last definition change.** The runs before it were graded against
  different instructions. The walk runs down the workspace's deployments from the newest and
  takes the oldest one still carrying the current hash of the graded agent's `AGENT.md`. Pass
  `since` to override it; with no deployment history the window falls back to `window_days`.
- **A run is graded again on the next schedule** until the definition changes, because the
  window is the definition's lifetime. `max_runs` bounds what that costs.
- **The window is walked.** Run listing yields runs newest first, pages lazily and takes no
  `since` or `until`, so the walk runs from the newest run down to the first one outside the
  window and a window holding more runs than a page still comes back whole.
- **Every run found is accounted for.** A run still going, one that declared no result and one
  whose artifacts could not be read are listed under `skipped_runs` with the reason, and
  `runs_found` equals `runs_evaluated + runs_skipped`.
- **A judge out of budget costs one run its judge checks, not its results.** The deterministic
  checks Python decided before the loop started are reported, the judge checks read `N/A`, the
  run counts as evaluated and never passes, and the window names the reason in a scope bullet.
  The recommendation pass is guarded the same way: a failure there is reported in place of the
  recommendation and the graded window still reports.
- **A graded run is `completed` or `failed`.** A run record speaks the platform's vocabulary
  (`pending`, `starting`, `running`, `cancelling`, `completed`, `failed`, `cancelled`,
  `skipped`) and an agent result speaks its own (`succeeded`, `failed`, `aborted`), so a run
  that finished well reads `completed` on the record and `succeeded` in the result.
- **One judge run per graded run.** `limits.max_tokens` counts from zero on each, so the limit
  in `defaults` means one evaluation and the cost of the job is the sum.
- **The job result carries the last loop's trace.** dlt stores one trace per job run, so a
  batch output counts turns and tokens over its evaluations instead.
- **An empty window reports to the log.** Right after a definition change the graded agent
  has not run yet. A job whose loop never started has no trace, and `_finish` reads one on any
  returned dict carrying `status`, so an empty window prints its report and returns `{}`. A
  window that found runs and graded none raises.
- **The recommendation is written over a window only.** A change to the instructions the
  agent followed rests on a pattern across runs. The scheduled job makes one more judge call
  after the window is graded, given the broken checks with how many runs broke each and a few
  of the reasonings, and writes one to three bullets naming the file and the section to
  change.

Deploy one or the other. An agent watched by both is graded twice.

#### Inputs and where a default lives

Every input is a parameter of the deployment function above. A workspace changes a default by
editing that parameter; a single run overrides one with `-c <name>=...`, and a job section in
`config.toml` overrides it for every run of that job.

| input | per-run deployment | scheduled deployment | default |
|---|---|---|---|
| `inspector_run_id` | the run graded; empty on a trigger, then `prev_run_id` | unused | `""` |
| `inspector_job_ref` | the job whose latest run is graded when no run id is given | the job whose window is graded | `""`, and the inspector's job ref on the scheduled one |
| `max_runs_read` | bounds `single_run_scope` | the same, on every run in the window | `DEFAULT_MAX_RUNS_READ` in `checks.py`, 5 |
| `window_days` | unused | how far back the window reaches with no deployment history | `DEFAULT_WINDOW_DAYS` in `checks.py`, 7 |
| `max_runs` | unused | inspector runs one scheduled job grades | `DEFAULT_BATCH_RUNS` in `checks.py`, 25 |

`prepare_batch` also takes `since` to pin the window start. It is an argument of the function,
not a declared input, so a deployment that exposes it as a parameter gets a manifest warning
that the system prompt never mentions it.

### Triggers that would loop

Do not point an inspecting agent at `job.fail:*` in a workspace that runs an evaluator. The
selector expands onto every other job, the evaluator included, so a failing evaluation is
inspected and the inspection starts the evaluator again. Name the jobs, or tag them. A tag
that matches no job is reported at deploy time as `matched no job`.

Three mechanisms sit between a broad selector and a loop, and none of them replaces naming
the jobs: the inspecting agent aborts when the run it resolved belongs to an evaluator job or
to its own job; `no_agent_job_inspected` reports FALSE when an inspection reached one anyway,
so the loop shows up in the evaluation; a job event never fires on a manual run. dlt has no
manifest validation for this yet, because a selector is expanded to concrete refs at deploy
time and nothing compares the result against the jobs that run agents.

### Picking the judge model

An evaluator names no model, so the workspace sets one in the `AGENT__MODEL` variable. It
takes a `provider:model` id on any provider, and an alias where the provider has one. A model
at least as capable as Claude Sonnet 5 is enough: the judge reads bounded windows and the
deterministic results, and every check is a narrow question with a three-value answer.

| Provider | Model meeting the bar | Alias | Step up when needed |
|---|---|---|---|
| Anthropic | `anthropic:claude-sonnet-5` | `sonnet` | `opus` |
| OpenAI | `openai:gpt-5.4-mini` | `gpt-mini` | `gpt` (`gpt-5.5`) |
| Azure OpenAI | `azure:<your deployment>` | none | a larger deployment |
| Google | `google:gemini-3.5-flash` | `gemini` | `gemini-pro` |

Step up only for a check that gives wrong outcomes after its rubric was fixed.

How the evidence arrives decides whether a model answers inside the limits. A judge handed
bounded windows answers in two turns on every provider in the table. Where an evaluator does
need `local`, grade a known run by hand on the model you mean to pin and read the trace: a file
the checks do not name, or the same file at several offsets, is budget the run needed for
answers. Raise `max_tokens` last, since a larger budget buys more of the same behaviour.

`agent.model`, `agent.api_key`, `agent.api_url` and `agent.api_version` are one set: a run
takes all four from the workspace or all four from the runtime. Setting `api_key` alone leaves
`model` unset, so the run sends the agent's default model to your endpoint and gets `401 API
key is invalid`. Set them as workspace variables, which arrive on the runner as environment
and override `.dlt/secrets.toml`:

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

### Running an evaluation by hand

```bash
dlthub local run job_inspector_eval -c inspector_run_id=<run id>
```

```bash
dlthub local run job_inspector_eval -c inspector_job_ref=jobs.job_inspector
```

Without inputs the evaluator reads the `prev_run_id` of its own run, which the scheduler sets
when the trigger started it. The resolution order is the given run id, then `prev_run_id`,
then the latest run of the given job ref, then the latest run of the job a `job.success:` or
`job.fail:` trigger names, then `aborted`.

The JWT that `dlthub login` writes expires after about an hour, so a fetcher passes a
credentials object the SDK renews through. A static token makes a long evaluation fail halfway
with `token_expired`.

### Replaying an evaluation offline

Capture everything one evaluation reads into a directory and read it back from there to
re-run that evaluation against a changed check without the platform:

```python
import checks as C

C.capture(C.SdkFetcher.connect(), "<run id>", "captures/run-42")
prep = C.prepare({"run_id": "local"}, fetcher=C.FileFetcher("captures/run-42"),
                 inspector_run_id="<run id>")
```

A fetch that fails is captured as absent rather than raised, so a partial capture still
replays and the checks see what the evaluation would have seen.

`job-inspector-eval` keeps nine captured runs under
`tests/job_inspector_eval/fixtures/captured/`, each named after the failure it shows.
`tools/scrub_capture.py` replaces every identifier before a capture lands in git, and a test
holds each fixture file to that. Three carry a reviewed answer for every judge check, and the
summary each renders is a golden file, so a diff on one is a change in what the reader reads.
A further test merges captures into one root and runs the batch path over them.

### What an evaluation reports

`passed` is true when no check is FALSE, every open check came back answered, and at least
one check was decided. A judge response that is empty or cut off leaves checks unanswered and
fails the evaluation. `pass_rate` is `TRUE / (TRUE + FALSE)`, so `N/A` never moves it. It sits
beside `decided_count` and `na_count` in the summary, because a rate over a third of the
checks reads the same as a rate over all of them.

Constrained decoding guarantees the schema, not that a model fills it as declared. `checks`
has come back as a JSON string, so `_judge_checks` also reads a double encoding, a
`{"checks": ...}` wrapper, a map keyed by check id, per-entry serialisation and a trailing
comma. A shape it cannot read is named in the summary and fails the evaluation, rather than
passing on the deterministic results alone.

A category verdict counts the checks that broke when one run is graded and takes their share
over a window, because one run decides tens of checks and a window thousands:

| verdict | one evaluation | a window |
|---|---|---|
| blocking | a security check came back FALSE, or 6 or more checks broke | a security check came back FALSE, or over 10% broke |
| needs attention | 3 to 5 broke | 2% to 10% broke |
| minor issues | 1 or 2 broke | under 2% broke |
| no findings | none broke, and at least one was decided | the same |
| not graded | the category decided nothing | the same |

### What the checks cannot see

- **Verbosity 0 hides the transcript from its checks.** A check that reads tool arguments or
  the agent's own statements needs the graded job's log at `agent.verbosity` 1. At 0 the log
  keeps tool names only, and those checks report `N/A` and say why. Keep an agent under
  evaluation at verbosity 1.
- **A parser that reads nothing decides nothing and fails the evaluation.** A log the parser
  could not read looks like an agent that called nothing. The run trace lists the tools the
  runtime recorded, so a trace with tool use and a transcript with none is a parser fault:
  the checks that read the transcript are held at `N/A`, the fault is recorded, and the
  evaluation comes back `failed`.
- **Line numbers run over the whole log.** The platform numbers `setup`, `program`, `runner`
  and `provider` lines in one sequence, so a job whose image build printed 197 lines has its
  first program line at 198. Evidence cites that number.
- **Judge checks are not deterministic.** Their accuracy was established on real runs rather
  than against a labelled set. A judge check that flips on the same input is a bug in its
  rubric; file it.
- **The judge reads model-authored text.** The body delimits it as content under evaluation
  and forbids following instructions found in it, which reduces the risk of prompt injection
  through a failed run's log rather than removing it.
- **The stored job result needs `dlthub-client` 0.28.5a1 or newer.** `job_runs.result` and
  `job_runs.trace` arrived there. On an older client, or on a run that declared no result, the
  result envelope the launcher prints at the end of the log is parsed instead, and a truncated
  log loses that envelope.

## Validation

`make validate-toolkits` checks every `agents/<name>/AGENT.md` in the workbench:

- frontmatter, if present, is valid YAML, and a stated `name` matches the folder
- the body is not empty, and every `{{ placeholder }}` in it is declared under
  `inputs.properties` or reachable under `run_context`
- `access` axes and verbs are known
- no `inputs.prompt`
- `summary` is headings over short bullets, the same headings on every run, with a table
  only at the end of the last section (§ the shape of `summary`)
- `output` declares `status` and `summary`, described and required, with the standard
  values; a contradicting declaration is an error, a missing one a warning
- `skills` and `rules` refs resolve in the toolkit or a declared dependency
- `defaults` and `defaults.limits` keys are known, and `defaults` sets no `model`

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
- `defaults` holds a sensible trigger and limits and no `model`; the `AGENT.md` says what
  model to pin. Nothing in `defaults` is a requirement.
- `make validate-toolkits` passes.

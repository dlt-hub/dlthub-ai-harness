# Background agents

A **background agent** is a toolkit item alongside skills, commands and rules. It runs
unattended: on a schedule, after a job fails, or when someone starts it from the web UI or
the command line.

This document is a guideline for authors. An agent definition is an `AGENT.md`, written much
like a `SKILL.md`. The working example is
[`job-inspector`](workbench/dlthub-platform/dlthub/agents/job-inspector/AGENT.md).

## Definition of terms

- **agent definition**: what the `AGENT.md` declares. The system prompt, the inputs and
  output, the tools, skills and rules the agent uses, and the access it needs. A toolkit ships
  definitions. (pydantic-ai, the framework that the default agent loop uses, calls this an
  `AgentSpec`.)
- **agent job**: a definition plus the settings that say how it operates in one workspace:
  model, token and turn limits, trigger, instructions, loop. A workspace declares it with
  `run.agent("<toolkit>:<name>", ...)`. (This is what pydantic-ai and claude-agent-sdk call an
  Agent, and what the dltHub web UI lists as one.)
- **agent run**: an execution of the agent job. It takes inputs (for example a job run id)
  and returns the agent output and an agent trace. Instructions, limits and model can be
  overridden for a single run through job configuration.
- **agent loop**: the binding to one agent framework. It runs the model turn by turn. Two are
  built in: `pydantic-ai`, the default, and `claude-agent-sdk`, which runs Claude Code and
  accepts Anthropic models only. A job selects one with `loop=` on `run.agent` or `agent.loop`
  in config. `claude-agent-sdk` is not officially supported. The agents in this repo are
  tested on `pydantic-ai` only. This document records the behavior of `claude-agent-sdk` as
  observed, not as a contract.

Everything below is about the first of these, the agent definition: writing it so that any
job built on it, and any run of that job, follows your instructions.

## Where it lives, where it installs

```
workbench/<toolkit>/dlthub/agents/<name>/AGENT.md
```

A definition is a folder, like a skill. It sits under `dlthub/agents/` because `agents/` holds
a host's own subagents, and dlt does not install a definition from there. The folder can also hold an `agent.py` that dlt runs
around the loop (§ code around the loop) and the modules it imports.
`dlthub ai toolkit install <toolkit>` copies the folder to `.claude/dlthub/agents/<name>/`.
On other hosts the target is `.cursor/dlthub/agents/` or `.agents/dlthub/agents/`. The
`dlthub/` folder keeps it apart from the native subagents that the hosts scan for
(`.claude/agents/`, `.codex/agents/`). A workspace refers to it as `<toolkit>:<name>`. The
toolkit index `.dlt/.toolkits` goes with every deployment, so the reference resolves on the
runner as it does locally. The toolkit ships the file and dlt runs it.

## Anatomy of `AGENT.md`

YAML frontmatter, then a markdown body. **The frontmatter declares what the agent has, and
the body is its system prompt.** Only the body is required: a file with no frontmatter is a
valid definition, named after its folder, with the standard output.

| field | meaning |
|---|---|
| `name` | the folder name. State it only to have it in the file |
| `description` | what the agent does and when to run it. Shown in the UI |
| `tools` | feature groups of the dlthub MCP server the agent gets, and nothing else (§ tools) |
| `skills`, `rules` | `<toolkit>:<name>` refs to components the agent uses (§ skills and rules) |
| `access` | what the agent can touch: `local`, `data`, `context` (§ access) |
| `inputs` | JSON Schema of what the agent takes. Every input is a job configuration key (§ inputs) |
| `output` | JSON Schema of what the agent returns. `status` and `summary` are always in it (§ output) |
| `defaults` | settings that the agent job and the agent run can override: `limits`, `loop_run_args`. `model` exists, but shipped toolkits must not set it (§ defaults, § the model) |
| body | the system prompt, a template over `inputs` (§ the body) |

### `tools`

Feature groups of the dlthub MCP server, the platform-side tools: `jobs`, `logs`,
`telemetry`, `workspace`, `pipeline`, `toolkit`, `secrets`, `context`, `config`, plus
whatever other plugins contribute. The agent gets exactly the groups listed, not the
server's interactive defaults, and within a group only the tools its `access` covers
(§ access). No `tools`, no server.

```yaml
tools: [jobs, logs, telemetry]
```

### `skills` and `rules`

References to components of the same toolkit or one of its declared dependencies, as
`<toolkit>:<name>`. Skills are what the agent can use. How they reach the model depends on
the loop. pydantic-ai inlines their text into the system prompt. claude-agent-sdk lists them
by name and loads them on demand. Rules are inlined into the system prompt on every loop.
Only the listed components reach the agent, and nothing else installed in the workspace
does. A reference that does not resolve is skipped with a warning, and the agent runs with
less.

```yaml
skills: [dlthub-platform:debug-deployment]
rules: [init:dlthub-workspace, dlthub-platform:job-resources]
```

### `access`

What the agent can touch, per axis, as one verb or a list. An empty block wires no file tool
and no shell, and the MCP server serves only the toolkit catalog.

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
| `context` | `read` | runs, logs, job definitions and telemetry through the MCP server. The only verb served. `write`, `execute` and `deploy` are refused at manifest time until a runtime serves them |

`job-inspector` declares `local: read` and `context: read`. It investigates an open question
and cannot know in advance which file or which record answers it.

It does not declare `data`. It works from run records, logs, job definitions, telemetry and
source. `data` access puts workspace data in front of a model-driven process.

Credential files (`*secrets.toml`, `.env`) are never readable, whatever `local` says. A tool
the declaration does not cover is not offered to the model, and the agent trace of every run
lists the tools that were wired.

Repeat the policy in the body as explanation: "you are read-only" helps the model understand
its role, and the `access` block enforces it for the MCP tools. `local: execute` is an
exception. The shell has the credentials of the job, and nothing limits what it does with
them. If an agent has `execute` and data access, add a rule to the body that forbids data
writes.

### `inputs`

A JSON Schema. Every property is a job configuration key: `dlthub local run <job> -c
failed_run_id=...`, `jobs.<section>.<job>.failed_run_id` in `config.toml` or the
environment, or a run argument the trigger carries. The body refers to inputs as
`{{ name }}`. It refers to the run itself through `run_context`, which is implicit and never
declared:

- `{{ run_context.trigger }}`
- `{{ run_context.run_id }}`
- `{{ run_context.refresh }}`
- `{{ run_context.interval_start }}` and `{{ run_context.interval_end }}`, on a job with an
  interval

```yaml
inputs:
  type: object
  properties:
    failed_run_id:
      type: string
      description: run id of the failed job run to inspect
      entity_type: job-runs
  required: {}
```

- A required input with no value fails the run like any missing job argument. An optional
  one nobody supplied renders as empty text, so **the body must say what to do with partial
  input**: which combinations are workable, and when to abort.
- `required: {}` is how "nothing required" is written. `[]` works too.
- An input the body never names is a warning at manifest time, because nothing reads it.
- There is no `inputs.prompt`. The task is the body.

### Entities: `entity_type`

An input that names a workspace entity carries `entity_type`: `job-runs`, `job`, `pipeline`,
`dataset` or `workspace`. The agent receives the bare id (a run id, a job ref, a pipeline
name). dlt composes the entity reference `job-runs/<id>` when it reports.

Declaring it does two things:

1. The run reports the entity in its job result's `object` list, so the run shows up on
   that entity's page.
2. The **first** entity-typed input becomes `expose.object_input` in the deployment
   manifest, `{entity_type, input}`. The web UI uses it to offer the agent job on the entity
   page, for example on the row of a failed run. It also uses it to pick the input key for
   the entity.

Declare the same name with `entity_type` on an **output** property when the agent can act on
an entity other than its input. An output overwrites the input of the same name in `object`,
so an inspector that resolved a run from a job ref reports the run it actually inspected.

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

A declaration that contradicts them (`status` with other values, `summary` not a string)
fails validation, because dlt overwrites it and your intent is lost. A domain outcome gets
its own name: a data-quality agent returns `verdict`, not a second `status`.

Declare `status` and `summary` anyway. Then the file shows the full contract, and
`make validate-toolkits` checks that they carry the standard values.

Add the agent's own fields next to them. What to know about the schema:

- **The model sees the whole schema, descriptions and enums included.** A description is
  the only place that carries semantics. An enum says which values are legal, not when to
  pick which. Describe every field whose name does not say it all.
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
  stopped a job launching.

The `status` of the agent run decides what the job does. `succeeded` and `failed` complete
the run. `aborted` raises with `summary` as the message and the run fails, after the result
and the agent trace were delivered.

#### The shape of `summary`

The platform renders `summary` as markdown on the run page, and it is the only field a
reader sees without opening the result. Every agent writes it the same way:

- **Markdown headings over short bullets, and nothing else.** No text before the first
  heading, no text outside a bullet, no question or bracketed note next to a heading.
- **The same headings on every run of one agent**, in the same order, named for what that
  agent reports. Take the default for the kind of agent below and change it where the agent
  reports something else. Declare the set in the body and hold to it.
- **The finding comes first and the scope last.** The first section says what the run found.
  What it covered goes at the bottom, next to the detail a reader opens from there.
- **One or two plain sentences per bullet, one fact each.** Two verbs joined by `and` or
  `then` are two bullets.
- **A part of a finding is a bullet under it, nested one level.** Only `##` headings, so
  every heading is a section a reader can scan for.
- **What the run could not cover goes in `Scope`.** Inputs that could not be read, a window
  that was cut short. An agent with no `Scope` section puts them
  in its last section, which is what `job-inspector` does with `Confidence`.
- **A markdown table only as the last thing in the last section**, when the agent reports
  rows. Its headers are lowercase and name the field in the row. A row that measured nothing
  stays out. The count of such rows goes in `Scope` or in the tally above the table.
- **Every run id and job ref is a link**, wherever it falls. The text is the id in a code span
  and the target is `<web ui base>/w/<workspace id>/runs/<id>` for a run, `/jobs/<job ref>` for
  a job. `dlt_runtime.urls` builds that base from the API base url, which is how the CLI prints
  a run link.
- **Markdown only, no raw HTML.** The summary renderer in the web UI strips tags, so a
  `<details>` element folding a long list arrives as an empty section. A long list goes in as
  plain bullets.
- **Close every code span, and never escape a backtick with a backslash.** An unbalanced span
  swallows the rest of the line in the UI, and `\`` renders as itself.
- **No verdict label at the top.** State what was found. The other output fields carry the
  verdict.

State the shape in the body. `job-inspector` has the rules under "Summary format". An agent
that assembles its summary in Python around the loop splits what the model wrote into bullets
itself.

##### Default sections

An agent that investigates, inspects or analyzes an entity in the workspace takes the
sections `job-inspector` writes:

| heading | the bullets answer |
|---|---|
| `## Diagnosis` | What happened, where, and why. The bullet that carries the cause quotes its evidence with the source and the line |
| `## Recommendation` | What the reader does next: the target and the change, written as the instruction itself |
| `## Confidence` | What this rests on and what it leaves open. When nothing was left open, one bullet says so |

### `defaults`

Settings that the agent job can change. An agent run can change them again:

```yaml
defaults:
  limits: {max_turns: 30, max_tokens: 1000000}
  loop_run_args: {retries: 1}           # framework-specific; unknown keys are reported, not fatal
```

`limits.max_tokens` is counted by dlt after every turn.
`loop_run_args` are handed to the framework. `retries` is how often pydantic-ai lets the model
correct a failing tool call. Keys the loop does not know are listed in the agent trace as
ignored.

A definition sets no `trigger`. `to_agent_definition` drops `defaults` from the manifest
and the loop takes `model`, `limits` and `loop_run_args` from it, so a trigger declared here
does nothing. The trigger belongs to `run.agent(trigger=...)`, where the workspace declares
which of its own jobs the agent watches. `make validate-toolkits` rejects a
`defaults.trigger`.

Precedence, lowest first: loop default, `defaults` here, the agent job's arguments,
configuration at run time. A runtime value always wins. Put defaults here, and no
requirements.

### The model

`model` is an alias (`sonnet`, `opus`, `haiku`, `fable`, `gpt`, `gpt-mini`, `gpt-nano`,
`gemini`, `gemini-pro`) or a `provider:model` id. The workspace deploying the agent sets it
in one place, the `AGENT__MODEL` variable, which every agent job in that workspace reads.
`run.agent` also takes `model=`, and configuration outranks it, so a value in the deployment
code is silently beaten by the variable. Leave it out and the two cannot disagree.

A definition shipped in a workbench toolkit names no model. An alias resolves on Anthropic,
OpenAI and Google. An Azure workspace addresses a deployment on its own endpoint and has no
alias, so a shipped `model: sonnet` is a default it cannot resolve. `make validate-toolkits`
rejects one.

Say in the `AGENT.md` what to pin instead: the class of model the instructions were written
for, as "at least as capable as Claude Sonnet 5".

A definition cannot select a loop. The workspace selects it with `loop=` on `run.agent` or
with `agent.loop`. `claude-agent-sdk` takes Anthropic models only and is not officially
supported.

## The body

The body is the system prompt: who the agent is, what it produces, what "done" means, and
the task itself with its inputs named. It is a template: `{{ name }}` and `{{ a.b }}` are
substituted before the first turn, and that is the whole grammar. Write it like a skill, for
a reader that has the tools and none of the context.

What the model gets besides the body: the rules inlined, the skills listed or inlined, a
sentence naming the workspace folder and the temp folder for scratch files, the output schema
with its descriptions, and the tools that `access` and `tools` make available. On
claude-agent-sdk the workspace's `CLAUDE.md` loads as in any Claude Code session, while the
`.claude/rules` folder stays out. What it gets as the user turn is the agent job's
`instructions`, or a bare "Go ahead". Do not restate any of that.

What a body must do, with job-inspector as the example:

1. **State the role in two sentences, including the unattended setting.** "You run
   unattended, seconds after a job failed. An engineer reads your output only when the
   failure matters, so it must stand on its own."
2. **Define `succeeded`, `failed` and `aborted` for this agent.** The schema deliberately
   does not. Write the bar as a positive claim and name the failure mode you fear. With
   constrained decoding the cheap escape from `failed` is a guess dressed as success.
   "The distinction that matters is cause found versus cause not found, not whether the
   problem got solved."
3. **Say what to do with each input, and with its absence.** Inputs are usually optional.
   Name the fallbacks in order, and the point at which nothing is left to work on and the
   answer is `aborted`.
4. **Give the first steps concretely.** Which tool or command to run first, what to read,
   what the tell-tale signs are. A skill reference is good here. A skill the agent has is
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
    # `ingest` is a tag this workspace puts on its own jobs
    trigger="job.fail:tag:ingest",
    require={"profile": "access"},       # see "Profile"
    instructions="focus on the loader step",
)
```

`trigger` takes dlt trigger strings: `schedule:0 7 * * *`, `job.fail:<job ref or selector>`,
`job.success:...`. `job.fail:*` watches every job in the workspace. It expands at manifest
time and never includes the job that declares it. Before you use it, read "Trigger cycles". A
run started by hand or from the UI arrives with a `manual:` trigger and only the inputs it
was given, which is why the body must say what to do with empty input.

Every decorator argument overrides the matching `defaults`, and configuration overrides both.
`instructions` is the user turn of every run. The job is named after the definition
(`job_inspector`). Instead of a `<toolkit>:<name>` reference the workspace can point at a
folder holding an `AGENT.md` by its workspace-relative path. A function decorated with
`run.agent` can also be a definition on its own, or drive an installed one. See the dlt
documentation for that form.

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
its environment. Declare the profile alongside the `access` block. `access` decides which
tools the model is offered. The profile decides which credentials the job process holds.

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
authors apply it.

The profile has to be `configured` in the workspace. Workspace info lists which ones are. On
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

## Code around the loop: `agent.py`

An agent folder can ship an `agent.py` next to its `AGENT.md`. dlt imports it when a job that
references the agent runs, and calls two functions from it:

- `validate_input(inputs)` before the loop. `inputs` holds the declared inputs that have a
  value, plus `run_context`. The return value replaces the inputs, `None` keeps them, and
  raising `run.JobAbortedException(summary, output)` ends the run as `aborted` without calling
  the model.
- `validate_output(output)` after the loop. The return value replaces the output, `None`
  keeps it.

`job-inspector` uses it, so a workspace declares it by reference and writes no code:

```python
from dlt.hub import run

inspector = run.agent(
    "dlthub-platform:job-inspector",
    trigger="job.fail:tag:ingest",
    require={"profile": "access"},
)
```

The inspector's `agent.py` links its summary in `validate_output`.

dlt imports the folder as a package of its own, so `agent.py` imports the files next to it
relatively (`from .links import link_summary`) and two agents can each ship a `links.py`. An
agent folder imports only its own files.

Code that talks to the platform reads dlt's own `active().runtime_config` for the credential
(`api_key` or `auth_token`, `workspace_id`, `api_base_url`) rather than the environment. The
same call resolves from `.dlt/config.toml` locally and from the mounted configuration on the
runner, so there is nothing to guess about which keys the platform injects.

### Linking the runs and jobs a summary names

An agent writes a run id as a uuid, because that is what a person pastes into
`dlthub job runs logs`. It cannot write a link: its `run_context` carries the trigger, the
run id and the interval, and no workspace id or UI base. So the ids become links after the
loop, in `links.py`. A run id becomes a link to the run's page in the web UI, with the logs tab
open when the text around it is a log command, and a job ref becomes a link to the job's page.

The inspector's `agent.py` passes its output to `link_summary`, which runs
`linkify(summary, web_ui(), labels_from_platform(summary))`. `labels_from_platform` reads the
run number behind each id and makes it the link text, so a reader meets `#114` rather than a
uuid.

dlt puts the link around the code span, not inside it. A link inside a code span shows as raw
markup. So the inspector's `` `dlthub job runs logs <id>` `` is what the reader clicks.

## Trigger cycles

Do not point an agent at `job.fail:*` in a workspace that runs other agent jobs. The selector
expands onto every other job, those agent jobs included, so a failing agent run starts another
agent run, which can fail in turn. Name the jobs, or tag them. A tag that matches no job is
reported at deploy time as `matched no job`. A job event never fires on a manual run.

dlt does not validate this at deploy time. The selector expands to job refs, and nothing
compares them with the jobs that run agents.

## Picking a model

A shipped agent names no model, so the workspace sets one in the `AGENT__MODEL` variable. It
takes a `provider:model` id on any provider, and an alias where the provider has one. Pick a
model at least as capable as the class the `AGENT.md` names (§ the model). For `job-inspector`
that is Claude Sonnet 5.

| Provider | Model meeting the bar | Alias | Step up when needed |
|---|---|---|---|
| Anthropic | `anthropic:claude-sonnet-5` | `sonnet` | `opus` |
| OpenAI | `openai:gpt-5.4-mini` | `gpt-mini` | `gpt` (`gpt-5.5`) |
| Azure OpenAI | `azure:<your deployment>` | none | a larger deployment |
| Google | `google:gemini-3.5-flash` | `gemini` | `gemini-pro` |

Run the agent by hand on a known run with the model you plan to pin, then read the agent trace.
The same file read at several offsets uses budget the run needed for answers. Raise
`max_tokens` last, because a larger budget gives more of the same behavior.

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

## Testing without a model provider

`tests/agents/` declares `job-inspector` the way a workspace does,
`run.agent("dlthub-platform:job-inspector")`, and calls the agent job as a function. It runs on
dlt's pydantic-ai loop with pydantic-ai's `TestModel` as the model, so the definition, its
`agent.py`, the rendered prompt, the output schema and the job result are checked without a
model provider.

## Validation

`make validate-toolkits` checks every `dlthub/agents/<name>/AGENT.md` in the workbench:

- no `AGENT.md` sits under the toolkit's `agents/`, where dlt does not look for it
- the folder holds only the `AGENT.md` and Python modules, since an install copies it whole

- frontmatter, if present, is valid YAML, and a stated `name` matches the folder
- the body is not empty, and every `{{ placeholder }}` in it is declared under
  `inputs.properties` or reachable under `run_context`
- `access` axes and verbs are known
- no `inputs.prompt`
- every `inputs` and `output` property names a `type`. An enum without one breaks Anthropic
- `entity_type` values are known, sit on string properties, and agree between an input and
  the output of the same name
- `output` declares `status` and `summary`, described and required, with the standard
  values. A contradicting declaration is an error, a missing one a warning
- `skills` and `rules` refs resolve in the toolkit or a declared dependency
- `defaults` and `defaults.limits` keys are known, and `defaults` sets no `model` and no
  `trigger`
- `agent.py`, when present, parses and defines `validate_input` and `validate_output` as
  functions

dlthub validates again when it generates the deployment manifest. The body is required, the
name falls back to the folder, `access` is checked, an unknown `entity_type` is refused, a
`prompt` input is refused, an input the body never mentions is a warning, and a skill or rule
that does not resolve in the workspace is skipped with a warning.

## Authoring checklist

- The folder name is the agent's name. `description` says when to run it.
- `tools` lists only the feature groups the task needs, and `access` only the verbs it needs.
- Every input has a `description`, entity inputs have `entity_type`, and the body names every
  input and says what to do when it is empty.
- `output` keeps `status` and `summary` as declared above and describes every field of its
  own. An entity that the agent can resolve itself is an output property too.
- The body defines succeeded, failed and aborted for this agent, gives the first steps, and
  defines every enum.
- `defaults` holds sensible limits and no `model` and no `trigger`. The `AGENT.md` says
  what model to pin and the deployment sets the trigger. Nothing in `defaults` is a
  requirement.
- Code that runs around the loop lives in the folder's `agent.py`, and the folder imports only
  its own files.
- `make validate-toolkits` passes.

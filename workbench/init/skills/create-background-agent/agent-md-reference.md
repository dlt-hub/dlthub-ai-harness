# `AGENT.md` frontmatter

This file owns every frontmatter field of an agent definition. The procedure is in
[SKILL.md](SKILL.md); the shape of `summary` is in [summary-format.md](summary-format.md) and
everything about deploying in [deployment.md](deployment.md).

Reference: job configuration, which every input is a key of,
`https://dlthub.com/docs/hub/pipeline-operations/job-configuration.md`

| field | meaning |
|---|---|
| `name` | the folder name; state it only to have it in the file |
| `description` | what the agent does and when to run it; shown in the UI |
| `tools` | feature groups of the dlthub MCP server the agent gets, and nothing else |
| `skills`, `rules` | `<toolkit>:<name>` refs to components the agent uses |
| `access` | what the agent may touch: `local`, `data`, `context` |
| `inputs` | JSON Schema of what the agent takes; every input is a job configuration key |
| `output` | JSON Schema of what the agent returns; `status` and `summary` are always in it |
| `defaults` | settings the agent job and the run may override: `model`, `limits`, `loop_run_args` |
| body | the system prompt, a template over `inputs` |

## `tools`

Feature groups of the dlthub MCP server, the platform-side tools: `jobs`, `logs`, `telemetry`,
`workspace`, `pipeline`, `toolkit`, `secrets`, `context`, `config`, plus whatever other plugins
contribute. The agent gets exactly the groups listed, not the server's interactive defaults, and
within a group only the tools its `access` covers. No `tools`, no server.

```yaml
tools: [jobs, logs, telemetry]
```

## `skills` and `rules`

References to components of the same toolkit or one of its declared dependencies, as
`<toolkit>:<name>`. Skills are what the agent may invoke. How they reach the model depends on the
loop: pydantic-ai inlines their text into the system prompt, claude-agent-sdk lists them by name
and loads them on demand. Rules are inlined into the system prompt on every loop. Only the listed
components reach the agent; nothing else installed in the workspace does. A reference that does
not resolve is skipped with a warning, and the agent runs with less.

```yaml
skills: [dlthub-platform:debug-deployment]
rules: [init:dlthub-workspace, dlthub-platform:job-resources]
```

## `access`

What the agent may touch, per axis, as one verb or a list. An empty block wires no file tool and
no shell. What it leaves of the MCP server depends on `tools`: with no groups listed there is no
server at all, and with groups listed the server serves the toolkit catalogue alone, since every
other group's tools need an axis.

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

Credential files (`*secrets.toml`, `.env`) are never readable, whatever `local` says. A tool the
declaration does not cover is not offered to the model, and the trace of every run lists the tools
that were wired.

Repeat the policy in the body as explanation: "you are read-only" helps the model understand its
role, and the `access` block enforces it for the MCP tools. `local: execute` is the exception: the
shell runs under the job's credentials and nothing gates what it does with them, so an agent with
`execute` and data access needs an explicit rule in the body never to write data.

## `inputs`

A JSON Schema. Every property is a job configuration key: `dlthub local run <job> -c
failed_run_id=...`, `jobs.<section>.<job>.failed_run_id` in `config.toml` or the environment, or a
run argument the trigger carries. The body refers to inputs as `{{ name }}` and to the run itself
as `{{ run_context.trigger }}`, `{{ run_context.run_id }}`, `{{ run_context.refresh }}` and, on a
job with an interval, `{{ run_context.interval_start }}` and `{{ run_context.interval_end }}`;
`run_context` is implicit and never declared.

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

- A required input with no value fails the run like any missing job argument. An optional one
  nobody supplied renders as empty text, so **the body must say what to do with partial input**:
  which combinations are workable, and when to abort.
- An input the run did not carry at all is also logged as an unresolved placeholder and listed
  in the trace under `unresolved_placeholders`. The text still renders empty, so a triggered run
  of an agent with optional inputs warns on every run and works as written.
- `required: {}` is how "nothing required" is written; `[]` works too.
- An input the body never names is a warning at manifest time: nothing would read it.
- There is no `inputs.prompt`. The task is the body.

### Entities: `entity_type`

An input that names a workspace entity carries `entity_type`: `job-run`, `job`, `pipeline`,
`dataset` or `workspace`. The agent receives the bare id (a run id, a job ref, a pipeline name);
dlt composes the entity reference `job-run/<id>` when it reports.

Declaring it does two things:

1. The run reports the entity in its job result's `object` list, so the run shows up on that
   entity's page.
2. The **first** entity-typed input becomes `expose.object_input` in the deployment manifest,
   `{entity_type, input}`. That is how the web UI offers the agent job from an entity, a failed
   run's row for `job-inspector`, and knows which key to pass the entity under.

Declare the same name with `entity_type` on an **output** property when the agent may end up
acting on a different entity than it was given: an output overwrites the input of the same name in
`object`, so an inspector that resolved a run from a job ref reports the run it actually inspected.

Put that property in `required`. A grader, and anything else reading the run afterwards, resolves
the entity from it, and a model leaves an optional field out: the checks over that artifact then
answer `N/A` and the run is graded blind.

## `output`

A JSON Schema of the agent output. Two properties are the contract every agent shares and dlt adds
them, with their descriptions, when a definition leaves them out:

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

**dlt writes its own description over both**, whatever the file says. The model reads dlt's text,
so what `succeeded`, `failed` and `aborted` mean for this agent belongs in the body. A
description written here documents the contract for the next author.

Declare them anyway: the file then shows the whole contract, and `make validate-toolkits` checks
they carry the standard values. A declaration that contradicts them (`status` with other values,
`summary` not a string) fails validation, because dlt would overwrite it and lose your intent. A
domain outcome gets its own name: a data-quality agent returns `verdict`, not a second `status`.

Add the agent's own fields next to them. What to know about the schema:

- **The model sees the whole schema, descriptions and enums included.** A description is the only
  place semantics travel; an enum says which values are legal, not when to pick which. Describe
  every field whose name does not say it all.
- **Constrained decoding guarantees shape, not truth.** A misread field is a confident,
  schema-valid, wrong answer. The body has to define what each value means.
- **The schema reaches the model as declared.** dlt changes one thing: `entity_type` moves into
  `$comment`, because strict validators reject keywords they do not know. Nothing is added or
  relaxed on your behalf, so write what the provider accepts. For example, Anthropic's structured
  output rejects `minimum`, `maximum` and `minLength`. Put numeric bounds in the description.
- **Every object names its `properties`.** A bare `type: object` means "any object", which a
  strict validator refuses, so OpenAI's structured output falls back or rejects the schema. A
  field Python fills after the loop is declared as fully as one the model writes.
- **Every property names its `type`, an enum included.** Anthropic's schema transformer
  refuses a property carrying `enum` and no `type` with `Schema must have a 'type', 'anyOf',
  'oneOf', or 'allOf' field`, and the run fails on the first model call. Write `type: string`
  beside the enum.
- **At most 24 optional properties, nested ones counted.** Anthropic rejects a larger schema
  with `Schemas contains too many optional parameters (N), which would make grammar compilation
  inefficient`, and the run fails on the first model call. A property listed in its object's
  `required` does not count, and `required` inside a nested object binds only when the model
  writes that object, so every nested property of a field Python fills belongs in one.
- **Keep the schema small.** The model reads all of it on every run, and a large one has stopped a
  job launching. An agent that reports per-item results keeps the item's schema to the fields a
  reader acts on, and a test holds the whole `output` under 8,000 characters.

The agent run's `status` decides what the job does: `succeeded` and `failed` complete the run;
`aborted` raises with `summary` as the message and the run fails, after the result and trace were
delivered.

The shape `summary` itself must take is in [summary-format.md](summary-format.md).

## `defaults`

Settings the agent job may set differently and a run may override again:

```yaml
defaults:
  limits: {max_turns: 30, max_tokens: 1000000}
  loop_run_args: {retries: 1}           # framework-specific; unknown keys are reported, not fatal
```

`limits.max_tokens` is counted by dlt after every turn. `loop_run_args` are handed to the
framework: `retries` is how often pydantic-ai lets the model correct a failing tool call; keys the
loop does not know are listed in the trace as ignored.

A definition sets no `trigger`. `to_agent_definition` drops `defaults` from the manifest and the
loop takes `model`, `limits` and `loop_run_args` from it, so a trigger declared here does nothing.
The trigger belongs to `run.agent(trigger=...)`, where the workspace declares which of its own
jobs the agent watches. `make validate-toolkits` rejects a `defaults.trigger`.

Precedence, lowest first: loop default, `defaults` here, the agent job's arguments, configuration
at run time. A runtime value always wins, so put here what should hold when nobody says otherwise,
and nothing that must hold.

## The model

`model` is an alias (`sonnet`, `opus`, `haiku`, `fable`, `gpt`, `gpt-mini`, `gpt-nano`, `gemini`,
`gemini-pro`) or a `provider:model` id. The workspace deploying the agent sets it in one place,
the `AGENT__MODEL` variable, which every agent job in that workspace reads. `run.agent` also takes
`model=`, and configuration outranks it, so a value in the deployment code is silently beaten by
the variable; leave it out and the two cannot disagree.

A definition shipped in a workbench toolkit names no model. An alias resolves on Anthropic, OpenAI
and Google; an Azure workspace addresses a deployment on its own endpoint and has no alias, so a
shipped `model: sonnet` is a default it cannot resolve. `make validate-toolkits` rejects one.

Say in the `AGENT.md` what to pin instead: the class of model the instructions were written for,
as "at least as capable as Claude Sonnet 5".

## The agent loop

The framework that runs the model turn by turn. Two are built in: `pydantic-ai`, the default, and
`claude-agent-sdk`, which runs Claude Code and accepts Anthropic models only. A job selects one
with `loop=` on `run.agent` or `agent.loop` in config. `claude-agent-sdk` is not officially
supported: the agents in this repo are written for and tested on `pydantic-ai`, and what the other
loop does is recorded as observation rather than as a contract. On claude-agent-sdk the
workspace's `CLAUDE.md` loads as in any Claude Code session, while the `.claude/rules` folder
stays out.

`loop: claude-agent-sdk` is the model decision by another name, since it takes Anthropic models
only. Leave it to the workspace: an agent pinned to it runs on one provider.

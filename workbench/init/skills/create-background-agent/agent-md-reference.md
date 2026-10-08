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
| `tools` | feature groups of the dlthub MCP server the agent gets |
| `skills`, `rules` | `<toolkit>:<name>` refs to components the agent uses |
| `access` | what the agent may touch: `local`, `data`, `context` |
| `inputs` | JSON Schema of what the agent takes; every input is a job configuration key |
| `output` | JSON Schema of what the agent returns; `status` and `summary` are always in it |
| `defaults` | settings the agent job and the run may override: `model`, `limits`, `loop_run_args` |
| body | the system prompt, a template over `inputs` |

## `tools`

Feature groups of the dlthub MCP server, the platform-side tools: `jobs`, `logs`, `telemetry`,
`workspace`, `pipeline`, `toolkit`, `secrets`, `context`, `config`, `restore_pipeline`, plus
whatever other plugins contribute. The agent gets the groups listed rather than the server's
interactive defaults, and within a group only the tools its `access` covers. A file that lists no
`tools` starts no server.

```yaml
tools: [jobs, logs, telemetry]
```

### The catalogue

Step 5 of [SKILL.md](SKILL.md) asks for the page size of every list tool in the body. These are
the groups and what they hold, on `dlthub-client` 0.28.7. Check your own workspace with
`dlthub ai mcp run --stdio --no-default-features --features <group>`, since a dependency can
contribute tools to a group an agent already lists.

| group | access it needs | tools | page parameter |
|---|---|---|---|
| `jobs` | `context: read` | `dlthub_workspace_info`, `dlthub_this_run`, `dlthub_list_jobs`, `dlthub_get_job`, `dlthub_list_runs`, `dlthub_get_run`, `dlthub_get_run_result`, `dlthub_get_run_trace` | `limit` on both list tools: 20 by default, 100 at most, with `offset` to page. `members` on `dlthub_workspace_info`: 50 by default, 200 at most, 0 to skip |
| `logs` | `context: read` | `dlthub_get_run_logs`, `dlthub_grep_run_logs` | `max_lines` on `dlthub_get_run_logs`: 200 trailing lines by default, 5000 at most. `max_matches` on `dlthub_grep_run_logs`: 200 by default, 2000 at most, and `context` up to 50 lines a side |
| `telemetry` | `context: read` | `dlthub_telemetry_status`, `dlthub_list_pipeline_runs`, `dlthub_get_pipeline_run`, `dlthub_get_pipeline_run_trace`, `dlthub_list_pipelines`, `dlthub_list_datasets` | `limit` on the three list tools: 20 for runs, 50 for pipelines and datasets, 100 at most. `days` bounds the window: 7 for runs and pipelines, 30 for datasets, 365 at most. `max_chars` on `dlthub_get_pipeline_run_trace`: 20,000 by default, 200,000 at most |
| `config` | `context: read` | `dlthub_list_variables`, `dlthub_get_configuration_files` | none |
| `restore_pipeline` | `context: read` and `data: read` | `dlthub_restore_pipeline_from_run`, `dlthub_restore_pipeline` | `days` on `dlthub_restore_pipeline`: 30 by default, 365 at most |
| `context` | `context: read` | `search_dlthub_sources` | none |
| `pipeline` | `data: read` | `list_tables`, `get_table_schema`, `get_table_create_sql`, `preview_table`, `execute_sql_query`, `get_row_counts`, `get_local_pipeline_state`, `export_schema` (`local: write` too) | none; bound `execute_sql_query` with `LIMIT` in the SQL |
| `workspace` | `local: read`, plus `data: read` for `list_pipelines` | `list_pipelines`, `list_profiles`, `get_workspace_info` | none |
| `secrets` | `local: read`, `local: write` for the update | `secrets_list`, `secrets_view_redacted`, `secrets_update_fragment` | none |
| `toolkit` | none | `list_toolkits`, `toolkit_info` | none |

What the table does not show, and a deployed run costs to find out:

- **`dlthub_list_runs` already carries the row counts.** Every row holds the run's
  `pipeline_run_summaries`: pipeline name, dataset, destination, status, duration and `total_rows`
  for each pipeline the run executed. `dlthub_get_run` adds nothing on that score and costs a call
  a run, so a body that says to call it per row spends the budget for figures the listing handed
  over.
- **`dlthub_list_runs` without `job` returns the runs of archived jobs beside the live ones.** The
  workspace-wide listing has no archived filter; only `dlthub_list_jobs` takes one. Two pages of
  60 can fill with jobs nobody deploys any more and reach back days further than the agent
  intended. Pass `job` when the question is about one job, and say in the body how far back the
  window should reach.
- **`dlthub_get_run_logs` pages on `max_lines`, not `limit`,** and returns trailing lines, so
  raising it is how a truncated traceback comes back whole.

## `skills` and `rules`

References to components of the same toolkit or one of its declared dependencies, as
`<toolkit>:<name>`. Skills are what the agent may invoke. How they reach the model depends on the
loop: pydantic-ai inlines their text into the system prompt, claude-agent-sdk lists them by name
and loads them on demand. Rules are inlined into the system prompt on every loop. Only the listed
components reach the agent; nothing else installed in the workspace does. A reference that does
not resolve is skipped with a warning, and the agent runs with less.

**Inlining is paid once a turn.** An inlined component's characters join the system prompt, which
every turn resends, so a 9,500-character rule on a 20-turn run is 190,000 characters of context.
List what the agent decides with, and read each component as the agent gets it: a rule written for
an interactive session carries setup commands, a toolkit index and instructions to explain each
step to the user, and an unattended agent has no user, no shell without `local: execute`, and no
toolkit to install. Dropping one such rule cut a measured system prompt by 29% with no change in
what the agent found.

```yaml
skills: [dlthub-platform:debug-deployment]
rules: [dlthub-platform:job-resources, dlthub-platform:profiles]
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
| `data` | `read`, `write` | workspace data through the MCP server's data tools. `read` offers the read tools only and restricts SQL to `SELECT`. The tools attach a local dlt pipeline, which an agent job on the platform has no state for, so they fail at run time: see "Rows come through a hook" below. Mapping the verb to a dlt profile is planned |
| `context` | `read` | runs, logs, job definitions and telemetry through the MCP server. The only verb served; `write`, `execute` and `deploy` are refused at manifest time until a runtime serves them |

Credential files (`*secrets.toml`, `.env`) are never readable, whatever `local` says. A tool the
declaration does not cover is not offered to the model, and the trace of every run lists the tools
that were wired.

### Rows come through a hook

Every data tool takes a `pipeline_name` and restores that pipeline from `pipelines_dir` under the
active profile. An agent job runs on `access` in a fresh run directory, and the pipelines wrote
their state on `prod` on another machine, so `.dlt/state/access/pipelines/<name>` does not exist
and the call comes back with `No local state found`. Nothing catches this earlier: the spec
validates, the deployment succeeds, the MCP server starts and the model is offered the tools.

So an agent that reads warehouse rows takes them in `validate_input` with `dlt.dataset()` and
hands the model a rendered table, and its `access` block leaves `data` out. "Row evidence through
a hook" in [deployment.md](deployment.md) has the code.

The `restore_pipeline` group is the other route. `dlthub_restore_pipeline_from_run` and
`dlthub_restore_pipeline` read the pipeline's state back from the destination telemetry recorded,
after which the `pipeline` tools work on it by name. It costs the run a model turn and a sync, it
grants `data: read` to the model for the rest of the run, and it fails unless the profile the job
runs on holds credentials for that destination. Take it where the agent cannot know in advance
which pipeline it will need; take the hook everywhere else.

Repeat the policy in the body as explanation: "you are read-only" helps the model understand its
role, and the `access` block enforces it for the MCP tools. `local: execute` is the exception: the
shell runs under the job's credentials and nothing gates what it does with them, so an agent with
`execute` and data access needs an explicit rule in the body never to write data.

## `inputs`

A JSON Schema. Every property is a job configuration key: `dlthub local run <job> -c
failed_run_id=...`, `jobs.<section>.<job>.failed_run_id` in `config.toml` or the environment, or a
run argument the trigger carries. The body refers to inputs as `{{ name }}` and to the run itself
as `{{ run_context.trigger }}`, `{{ run_context.run_id }}`, `{{ run_context.refresh }}`,
`{{ run_context.interval_start }}` and `{{ run_context.interval_end }}`; `run_context` is implicit
and never declared.

### The interval pair is optional, `schedule:` included

`interval_start` and `interval_end` are `NotRequired` on `TJobRunContext`: the runtime fills them
or it does not, and a body that reads one has to work when it is empty. What dlt computes per
trigger is in `compute_run_interval`: `schedule:<cron>` and `every:<period>` carry a real window,
and `once:`, `manual:`, `http:`, `webhook:`, `tag:`, `deployment:`, `job.success:` and `job.fail:`
are point-in-time, where `interval_start` equals `interval_end` and the pair says nothing.

A deployed agent job on a `schedule:` trigger was measured without the pair at all. The body
rendered `{{ run_context.interval_end }}` as empty text and the loop logged `unresolved
placeholders: run_context.interval_end`, and the run was wasted. "Schedule" reads like "interval"
and is not a promise of one. So name a fallback for the window the agent audits, usually an
explicit input with today's date behind it, and assert the placeholder list is empty offline
before you deploy: "Check it offline, before it costs a run" in [deployment.md](deployment.md).

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
- An input the run did not carry at all is listed in the trace under
  `unresolved_placeholders`. The text renders empty and the run works as written. From dlt
  1.30.1a1 a declared optional input left unset is not warned about; the warning is kept for a
  placeholder naming something the file does not declare, and for a required input that is
  missing.
- `required: {}` is how "nothing required" is written; `[]` works too.
- An input the body never names is a warning at manifest time: nothing would read it.
- There is no `inputs.prompt`. The task is the body.

### Entities: `entity_type`

An input that names a workspace entity carries `entity_type`: `job-run`, `job`, `pipeline`,
`dataset` or `workspace`. The agent receives the bare id (a run id, a job ref, a pipeline name);
dltHub composes the entity reference `job-run/<id>` when it reports.

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

A JSON Schema of the agent output. Two properties are the contract every agent shares and dltHub adds
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

**dltHub writes its own description over both**, whatever the file says. The model reads dltHub's text,
so what `succeeded`, `failed` and `aborted` mean for this agent belongs in the body. A
description written here documents the contract for the next author.

Declare them anyway: the file then shows the whole contract, and `make validate-toolkits` checks
they carry the standard values. A declaration that contradicts them (`status` with other values,
`summary` not a string) fails validation, because dltHub would overwrite it and lose your intent. A
domain outcome gets its own name: a data-quality agent returns `verdict`, not a second `status`.

Add the agent's own fields next to them. What to know about the schema:

- **The model sees the whole schema, descriptions and enums included.** A description is the only
  place semantics travel; an enum says which values are legal, not when to pick which. Describe
  every field whose name does not say it all.
- **Constrained decoding guarantees the shape of the output alone.** A misread field comes back
  confident, schema-valid and wrong. The body has to define what each value means.
- **The schema reaches the model as declared.** dltHub changes one thing: `entity_type` moves into
  `$comment`, because strict validators reject keywords they do not know. Nothing is added or
  relaxed on your behalf, so write what the provider accepts. For example, Anthropic's structured
  output rejects `minimum`, `maximum`, `minLength` and `maxLength`. Put the bound in the
  description.
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

`limits.max_tokens` is counted by dltHub after every turn. `loop_run_args` are handed to the
framework: `retries` is how often pydantic-ai lets the model correct a failing tool call; keys the
loop does not know are listed in the trace as ignored.

### What `max_turns` counts

`max_turns` is pydantic-ai's `request_limit`, so it counts model requests. The run ends on
`UsageLimitExceeded: The next request would exceed the request_limit of <n>`.

From **dlt 1.31.0** the job log counts the same thing: it prints one `turn N` line a request, and
the run header and `trace["turn_count"]` agree with it. `── succeeded ── 9 turns · 176,583
tokens ──` is nine model requests. Up to 1.30.1a1 the log printed a second line for the tool
results coming back, so a run at `max_turns: 10` reached `turn 20` in the transcript before it
died, and a budget read off the transcript was out by a factor of two.

Size a budget from the header and the trace, and write a cut-off into the body as a count of
requests, which is what the model itself experiences as its turns.

### How `max_turns` and `max_tokens` interact

`max_turns` is the budget and `max_tokens` is the ceiling it has to fit under. Every turn resends
the system prompt and the whole history, and `max_tokens` counts input and output across the
entire run, so the spend is roughly the turn count times a context that grows with it. A measured
agent on Sonnet came to about 45,000 tokens a turn: one run reached 1,073,446 tokens in 23 turns
and died on the ceiling, while the same audit finished in 4 turns for 157,241.

The first turn's tool results are the other half of this. A list tool's default page is 20 and its
cap is 100, and a model asked to list something reaches for the cap; that payload is resent on
every turn after it, so two oversized opening calls can spend a whole budget in seven well-behaved
turns. Step 5 of [SKILL.md](SKILL.md) says to name the page size in the body for every list tool
the agent calls, and "The catalogue" above has the parameter and the cap per tool.

So size `max_turns` from the tokens a turn costs, which the run trace reports, against the
`max_tokens` you are willing to spend. Raising `max_tokens` on its own buys a wandering agent more
turns to waste. A body that says where to stop is what brings the turn count down; the limit only
decides whether the run dies before it gets there.

A definition doesn't set a `trigger`. `to_agent_definition` drops `defaults` from the manifest and the
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

A definition shipped in an AI harness toolkit names no model. An alias resolves on Anthropic, OpenAI
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

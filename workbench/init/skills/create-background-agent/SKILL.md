---
name: create-background-agent
description: "Write a dltHub background agent: an AGENT.md that runs unattended on the platform, on a schedule, after a job fails, or when someone starts it from the web UI. Use when the user wants work to happen on its own after an event ('whenever a job fails, diagnose it for me', 'every Monday summarise what broke'), when they ask how to write, declare or deploy an AGENT.md, how to pick its access, tools, inputs or output, how to set run.agent or AGENT__MODEL, or how to ship an agent in a toolkit. Do NOT use for a host subagent in .claude/agents/, for scheduling a pipeline or a plain job (deploy-workspace), or for diagnosing one failure right now (debug-deployment). To grade an agent that already runs, use evaluate-background-agent."
---

# Create a background agent

A **background agent** is a toolkit item alongside skills, commands and rules. It runs
unattended: on a schedule, after a job fails, or when someone starts it from the web UI or the
command line. An agent is an `AGENT.md`, written much like a `SKILL.md`. The working example is
`workbench/dlthub-platform/dlthub/agents/job-inspector/AGENT.md`, installed as
`.claude/dlthub/agents/job-inspector/AGENT.md`.

**Essential reading**: AI harness `https://dlthub.com/docs/hub/ai-harness/introduction.md`,
triggers and scheduling `https://dlthub.com/docs/hub/pipeline-operations/triggers.md`, profiles
`https://dlthub.com/docs/hub/pipeline-operations/profiles.md`

Reference files beside this skill:

- [agent-md-reference.md](agent-md-reference.md) owns every frontmatter field.
- [summary-format.md](summary-format.md) owns the shape of `summary` and the link helper.
- [deployment.md](deployment.md) owns `run.agent`, the profile pin, triggers and the `AGENT__`
  variables.

## Terms

- **agent definition**: what the `AGENT.md` declares. The system prompt, the inputs and output,
  the tools, skills and rules the agent uses, and the access it needs. A toolkit ships
  definitions. This skill is about writing one.
- **agent job**: a definition plus the settings that say how it operates in one workspace: model,
  token and turn limits, trigger, instructions, loop. A workspace declares it with
  `run.agent("<toolkit>:<name>", ...)`.
- **agent run**: an execution of the agent job. It takes inputs, for example a job run id, and
  returns the agent output and a trace. Instructions, limits and model can be overridden for a
  single run through job configuration.

## 1. Decide whether this is an agent at all

Three things get confused with a background agent. Route back when one of them is what the user
wants:

- **A scheduled pipeline or a plain job.** The work is deterministic and a person wrote the code.
  That is `deploy-workspace` in **dlthub-platform**.
- **One failure the user wants explained now.** That is `debug-deployment`.
- **A host subagent.** A Claude Code agent in `.claude/agents/`, or the equivalent on another
  host, runs inside a conversation. A dltHub agent runs on the platform with no conversation
  around it, which is why it installs under `.claude/dlthub/agents/`.

A background agent is right when the decision needs a model, the work runs with nobody watching,
and the output stands on its own.

## 2. Scaffold the folder

```
agents/<name>/AGENT.md                              # in a workspace
workbench/<toolkit>/dlthub/agents/<name>/AGENT.md   # in a toolkit
```

A folder, like a skill, so a definition can grow supporting files. In a workspace put it at the
workspace root and point the deployment at the folder path. In a toolkit it goes under
`workbench/<toolkit>/dlthub/agents/<name>/`, and `dlthub ai toolkit install <toolkit>` copies it
to `.claude/dlthub/agents/<name>/` (`.cursor/dlthub/agents/`, `.agents/dlthub/agents/` on the
other hosts). The `dlthub/` segment is on both sides: a toolkit's plain `agents/` folder is the
host's own subagents folder, which dlt neither installs from nor validates, and the hosts scan
their own folders for native subagents. A
workspace refers to an installed agent as `<toolkit>:<name>`, and the workspace's toolkit index
(`.dlt/.toolkits`) travels with every deployment, so the reference resolves on the runner as it
does locally.

The file is YAML frontmatter and a markdown body. The frontmatter declares what the agent has,
and the body is its system prompt. Only the body is required: a file with no frontmatter is a
valid definition, named after its folder, with the standard output.

```yaml
---
name: <folder name>
description: what it does and when to run it
tools: []
access: {}
inputs:
  type: object
  properties: {}
  required: {}
output:
  type: object
  properties: {}
  required: [status, summary]
defaults:
  limits: {max_turns: 30, max_tokens: 1000000}
---
```

## 3. Declare what it has

Four fields, each the task's narrowest set. [agent-md-reference.md](agent-md-reference.md) has
the field table, the access axes and the verbs.

- `tools`: the feature groups of the dlthub MCP server the agent gets, and nothing else.
- `access`: what it may touch, per axis: `local`, `data`, `context`.
- `skills` and `rules`: `<toolkit>:<name>` refs to components it uses.

What the task knows in advance is the decision rule. `job-inspector` grants `local: read`
and `context: read`: it investigates an open question and cannot know which file or which record
answers it. An agent that answers a fixed list of questions grants nothing and declares no
`tools`: the code around its loop fetches every artifact those questions read before the loop
starts and hands the model bounded windows. Fetch the evidence in Python where the task is fixed,
and grant the axis where it is open.

`job-inspector` grants no `data`. It works from run records, logs, job definitions, telemetry and
source, and a `data` grant would put workspace data in front of a model-driven process.

### Hold the grant narrow

The declaration contains important guardrails. dlt wires only what `access` and `tools` name, so
a verb you leave out is a tool the model is never offered. Five rules carry most of it.

- **Stay on the `pydantic-ai` loop.** The shipped agents are written and graded against it, and
  the wiring described here is its wiring. Another loop brings its own toolset, which none of
  this has been checked against.
- **Leave `local: execute` out.** The shell and `RunPython` run in the job's own process under
  the job's credentials, and the rules that keep the file tools out of `*secrets.toml` and
  `.env` do not reach them. Workspace variables arrive as process environment, so an agent
  without `execute` has no way to read one. Grant it where the task has no other route, and
  write into the body what it may run.
- **Take the smallest destination access.** Leave `data` out where run records, logs, job
  definitions, telemetry and source answer the question. Where rows are the task, `data: read`
  against a read-only credential in the `access` profile is the whole grant.
- **List the fewest feature groups.** A group brings every tool it holds that the access covers.
  A dependency added to the workspace can contribute tools to a group the agent already lists,
  so keep the workspace to what it needs.
- **A deployment argument replaces the grant.** `access=` on a decorated function driving a
  definition through `agent=` replaces the whole block rather than merging it, so an argument
  naming one axis drops the others. Leave those arguments off and let the `AGENT.md` hold the
  grant, or repeat every axis the agent needs. A reference with no function behind it keeps the
  definition's lists and the same arguments are dropped. Step 6 and
  [deployment.md](deployment.md) have the rest of what the Python overrides.

The same five apply to an agent you adapt from a shipped definition. Copying an `AGENT.md` and
widening `access` or `tools` is the point where the grant stops being the one that was graded.

## 4. Declare `inputs` and `output`

`inputs` is a JSON Schema and every property is a job configuration key. An input that names a
workspace entity carries `entity_type`. The body must say what to do with partial input: which
combinations are workable, and when to abort.

`output` is a JSON Schema of what the agent returns. `status` and `summary` are the contract every
agent shares; declare them with the standard values so the file shows the whole contract. A
domain outcome gets its own name: a data-quality agent returns `verdict`.

Both fields are in [agent-md-reference.md](agent-md-reference.md), with the entity rules, the
schema constraints the providers impose, and the size bound.

## 5. Write the body

The body is the system prompt: who the agent is, what it produces, what "done" means, and the
task itself with its inputs named. It is a template: `{{ name }}` and `{{ a.b }}` are substituted
before the first turn, and that is the whole grammar. Write it as you would a skill, for a reader
that has the tools and none of the context.

What the model gets besides the body: the rules inlined, the skills listed or inlined, a sentence
naming the workspace folder and the temp folder for scratch files, the output schema with its
descriptions, and the tools `access` and `tools` bought. What it gets as the user turn is the
agent job's `instructions`, or a bare "Go ahead". Do not restate any of that.

Six points, with `job-inspector` as the example:

1. **State the role in two sentences, including the unattended setting.** "You run unattended,
   seconds after a job failed. An engineer reads your output only when the failure matters, so it
   must stand on its own."
2. **Define `succeeded`, `failed` and `aborted` for this agent.** The schema deliberately does
   not. Write the bar as a positive claim and name the failure mode you fear; with constrained
   decoding the cheap escape from `failed` is a guess dressed as success. "The distinction that
   matters is cause found versus cause not found, not whether the problem got solved."
3. **Say what to do with each input, and with its absence.** Inputs are usually optional. Name
   the fallbacks in order, and the point at which nothing is left to work on and the answer is
   `aborted`.
4. **Give the first steps concretely.** Which tool or command to run first, what to read, what
   the tell-tale signs are. A skill reference is good here; a skill the agent has is loaded on
   demand.
5. **List constraints as rules, not adjectives.** "Never edit code, never deploy, never re-run a
   job" beats "be careful".
6. **Define every enum the output declares.** A table of value and when it applies. Say what
   `unknown` or `low` means and that reporting it is a legitimate outcome.

State the summary sections in the body and hold to them. Take the default set for this kind of
agent from [summary-format.md](summary-format.md), which also carries the shape rules the
renderer imposes.

Keep the body under about two hundred lines. The rules and skills it references hold the platform
knowledge, so the body holds what this agent has to decide.

## 6. Deploy it

**STOP and show the deployment plan before writing it**: the trigger, the profile, the model
variable, and which jobs the agent watches. [deployment.md](deployment.md) has the declared form,
the decorated form for code around the loop, the trigger strings and the `AGENT__` variables.

The minimum: `run.agent("<toolkit>:<name>", trigger=..., require={"profile": "access"})`, and
`AGENT__MODEL` set once in the workspace.

The Python overrides the file, and [deployment.md](deployment.md) has the table of what each form
overrides. Write the `AGENT.md` as the whole definition and put in the deployment only what this
workspace changes, so the file stays the thing that was reviewed and graded.

Three stops apply to every agent job. [deployment.md](deployment.md) has the mechanics behind
each:

- **An agent job must never run on the `prod` profile.** The runtime defaults it to `access`. Pin
  `require={"profile": "access"}` so the declaration says so, and never override it with `prod`.
  This is rule 4 of the always-loaded `dlthub-platform` profiles rule.
- **`job.fail:*` with an evaluator in the workspace starts a loop.** Name the jobs to watch, or
  tag them.
- **`agent.verbosity` stays at 1**, the default. At 0 the job log keeps tool names only, and every
  check that reads tool arguments or the agent's own statements goes blind.

## 7. Run it by hand and read the result

Check the active profile first: on `dlthub local run` the `require` declaration is a warning
rather than a switch, so the run uses the active profile and reports the mismatch. Then run the
job with its inputs as configuration keys and read the job result it prints, both shown in
[deployment.md](deployment.md).

Read the trace against what you declared. A tool in it that the task does not need is an `access`
axis to drop. A turn count at the limit is a body that did not say where to stop.

## 8. Check it, then have it graded

- The folder name is the agent's name; `description` says when to run it.
- `tools` lists only the feature groups the task needs; `access` only the verbs it needs.
- `access` holds no `local: execute` and no `data` the task does not read, and the job leaves the
  loop at `pydantic-ai`.
- Every input has a `description`, entity inputs have `entity_type`, and the body names every
  input and says what to do when it is empty.
- `output` keeps `status` and `summary` as declared, and describes every field of its own; an
  entity the agent may resolve itself is an output property too.
- The body defines succeeded, failed and aborted for this agent, gives the first steps, and
  defines every enum.
- `defaults` holds sensible limits and no `model` and no `trigger`; the `AGENT.md` says what model
  to pin and the deployment sets the trigger. Nothing in `defaults` is a requirement.
- The deployment changes only what this workspace needs, since every argument it passes overrides
  the file.
- For an agent shipped in a toolkit: `make validate-toolkits` passes. It checks the frontmatter,
  the placeholders in the body, the `access` vocabulary, the `status` and `summary` contract, the
  component refs and the `defaults` keys. dlthub validates again when the deployment manifest is
  generated.

An agent that runs unattended is read by a person only when its output matters, so nothing tells
you whether it followed its own instructions. Hand over to (`evaluate-background-agent`) to write
a grader for it.

---
name: dlthub-router
description: "The entry point for building anything with dlthub. Use this skill to route the user to the right workflow toolkit and install it on demand. MUST use when the user asks 'what can you do', 'what can I build', 'what are toolkits', 'how do I build a pipeline', 'I want to pull data from a REST API', 'ingest from a SQL database', 'ingest CSVs from S3 into a warehouse', 'make reports / dashboards', 'transform / model my data', 'add data quality checks', 'how do I deploy / schedule a pipeline', 'I'm new to dlthub', 'where do I start', 'my deployed job failed', or seems unsure what to do next after setup. Also use whenever the user expresses a data-engineering goal but no matching workflow toolkit is installed yet — this skill installs it on demand. Do NOT use when the toolkit matching the user's intent is already installed — go straight to its entry skill instead; only route/install when the matching toolkit is missing. Do NOT use when a specific task is already in progress (debugging a pipeline, validating data, adding endpoints) and its toolkit is installed. Do NOT use when the user explicitly wants a guided end-to-end demo — use **quick-start** for that."
---

# dlthub-router

Route the user to the right toolkit and skill, then install it. **Fast path first** — the always-loaded toolkit index (in your project rules / `AGENTS.md`) already maps intent → toolkit → install command → entry skill, so you usually do **not** need any discovery round-trip.

> **Router vs handovers.** This skill handles **cold start** — picking and installing a toolkit when none relevant is installed. Once inside a workflow, a toolkit's `workflow.md` **handover** sections take over: they carry context forward (pipeline name, dataset, destination) and route to a specific skill. Do **not** use this skill mid-workflow when the relevant toolkit is already installed. But when a handover names a toolkit that **isn't installed yet**, that's your cue — install it via the index below, then follow the handover's entry point + context.

## Step 1: Route from the always-loaded index (fast path)

The `# toolkits` index is already in your context. Match the user's intent to a row, then:

1. **Install** it: `dlthub --non-interactive ai toolkit install <name>`
2. **Confirm** (Step 3) and **hand over** to that toolkit's entry skill (Step 4).

This needs **no MCP call** — the index is authoritative for the shipped toolkits and is the fast path. Use it whenever the intent matches a row.

## Step 2: Live discovery (fallback only)

Use this **only** when the index has no matching row (an unfamiliar need, or you suspect a newer toolkit exists):

- **Prefer MCP** — `list_toolkits` from `dlt-workspace-mcp` for the live catalog, then `toolkit_info <name>` for skill details.
- **CLI fallback** (MCP not connected): `dlthub --non-interactive ai toolkit list`, then `dlthub --non-interactive ai toolkit info <name>`.

Match intent to the best toolkit, then install as in Step 1. Toolkits marked `(installed: <version>)` are already available.

## Step 3: Verify install (only when needed)

**Skip this step** when the install output already confirms success and the new toolkit's entry skill is available in this session — that is all the confirmation you need. (MCP health was already checked at session start via `dlthub ai status`.)

Run `uv run dlthub ai status` only if:
- the install output was ambiguous or reported an error,
- the entry skill doesn't appear to be available, or
- the `dlt-workspace-mcp` server hasn't been verified this session (no session-start status check and no successful MCP call yet).

If status shows a **WARNING** about the MCP server (e.g. cannot be started), **fix it** using the error message before handing over.

## Step 4: Handover (no restart needed)

The `dlt-workspace-mcp` server is already running (installed with `init`) and toolkits reuse it — installing one adds **no new MCP server**, so continue in this session. Do **not** ask the user to restart; that would lose the conversation context.

1. **Load the new toolkit inline** — prefer `toolkit_info <name>` (MCP), which is agent-agnostic and returns the entry skill + workflow rule. If MCP is unavailable, read the installed files directly; the install path depends on the agent (`.claude/`, `.cursor/`, or `.agents/`) — e.g. `<agent-dir>/skills/<entry-skill>/SKILL.md` and the toolkit's workflow rule.
2. **Follow that workflow rule and start at the entry skill**, continuing the user's task with the context you already have. Do not start unrelated workflows on your own.
3. The new skills become natively registered (`/`-invocable, always-loaded workflow rule) on the next natural session start — no need to restart now.

> Exception: if a future toolkit ever ships its **own** MCP server (none do today), that server only starts on restart — suggest a restart **only** in that case, and use CLI fallbacks until then.

## Background agents

A **background agent** ships with a toolkit and runs on a trigger: after a job fails, on a schedule, or from the web UI. A workspace declares it once with `run.agent("<toolkit>:<name>", ...)`, and the platform runs it from then on, outside any conversation.

Route here when the user wants work to happen on its own after an event ("whenever a job fails, diagnose it for me", "I don't want to read logs every morning"). Install the toolkit as in Step 1, then follow its workflow rule for the deployment snippet.

**"my job failed" routes four ways.** Pick by where it ran, and by whether the user wants this failure handled or all future ones:

* A local pipeline or transformation run, fix it now → that toolkit's own debug skill, `debug-pipeline` or `debug-transformation`. A dlt **load job** in a failed load package belongs here, on the user's machine.
* A deployed **platform job run** failed, look at it now → `debug-deployment` in **dlthub-platform**.
* Every future failure of a deployed job, unattended → `job-inspector`, below.
* Nothing deployed yet → deploy first. The agent triggers on platform job runs, so it has nothing to watch until then.

```
capability                                                        → agent                              | install                                                     | declare
diagnose a failed platform job run, classify it and propose a fix → dlthub-platform:job-inspector       | dlthub --non-interactive ai toolkit install dlthub-platform | run.agent("dlthub-platform:job-inspector", trigger="job.fail:*")
grade an inspector diagnosis against the inspector's instructions → dlthub-platform:job-inspector-eval  | dlthub --non-interactive ai toolkit install dlthub-platform | run.agent("dlthub-platform:job-inspector-eval", trigger=[inspector.success, inspector.fail])
```

* `job-inspector` is read-only: it diagnoses and proposes a fix, it never edits code or redeploys.
* Neither agent names a model. Set `AGENT__MODEL` in the workspace to a `provider:model` id at least as capable as Claude Sonnet 5. The evaluator's `README.md` carries the full snippet and the model per provider.
* Keep `agent.verbosity` at 1, the default. At 0 the job log drops the tool arguments and thoughts the evaluator reads.

<!-- Loading the new skill/rule inline is a stopgap: until the harness can hot-reload skills/rules after install, newly installed components aren't natively registered until the next session start. Tracked in dlt-hub/dlthub-ai-workbench-internal#72. -->


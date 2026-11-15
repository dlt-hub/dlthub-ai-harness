# Deploy to dltHub Platform

This toolkit owns `.dlthub/platform/` in the workspace. It keeps nothing there yet; deploy records, when there are any, go to `.dlthub/platform/deploy/<environment>/`.

## Workflow Entry
**ALWAYS** start with **Setup runtime** (`setup-runtime`) — ensure workspace, dependencies, and runtime login are ready

## Core workflow
1. **Prepare workspace** (`prepare-deployment`, local-workspace toolkit) — split dev/prod credentials, set up production destination, declare the jobs
2. **Deploy pipeline** (`deploy-workspace`) — prepare scripts for production, run the jobs locally (`run-local-jobs`), deploy, launch, schedule

## Extend and harden
3. **Debug deployment** (`debug-deployment`) — check job status, view logs, diagnose failures
4. **Inspect failures unattended** (`job-inspector`) — background agent: runs after a job fails, reads the run record and the logs, follows the traceback into the workspace code, classifies the failure and proposes a fix naming the target and the change. Declare it with `run.agent("dlthub-platform:job-inspector", trigger=...)` and no profile (see the `profiles` rule, rule 4), and set `AGENT__MODEL` in the workspace, at least as capable as Claude Sonnet 5. "Background agents" in (`deploy-workspace`) `advanced-patterns.md` says why each of those matters
5. **Write a background agent** (`create-background-agent`) — a new `AGENT.md` for work that should run on its own after an event: the fields, the `access` decision, the summary shape, `run.agent`, the profile and the trigger strings

## Background agents
A **background agent** ships with a toolkit and runs on a trigger: after a job fails, on a schedule, or from the web UI. A workspace declares it once with `run.agent("<toolkit>:<name>", ...)`, and the platform runs it from then on, outside any conversation. Use one when the user wants work to happen on its own after an event ("whenever a job fails, diagnose it for me", "I don't want to read logs every morning").

**"my job failed" routes four ways.** Pick by where it ran, and by whether the user wants this failure handled or all future ones:
* A local pipeline or transformation run, fix it now → that toolkit's own debug skill. A dlt **load job** in a failed load package belongs here, on the user's machine.
* A deployed **platform job run** failed, look at it now → (`debug-deployment`).
* Every future failure of a deployed job, unattended → (`job-inspector`): `run.agent("dlthub-platform:job-inspector", trigger="job.fail:tag:<tag>")`. It is read-only: it diagnoses and proposes a fix, it never edits code or redeploys. `<tag>` is a tag the workspace puts on its own jobs, `run.pipeline(..., expose={"tags": ["ingest"]})`. The agent names no model: set `AGENT__MODEL` to a `provider:model` id at least as capable as Claude Sonnet 5, and `AGENT__API_KEY` to the key for that provider.
* Nothing deployed yet → deploy first. The agent triggers on platform job runs, so it has nothing to watch until then.

A new agent, not a shipped one → (`create-background-agent`).

## Handover to other toolkits

### Outgoing (from dlthub-platform)

- **rest-api-pipeline** → `debug-pipeline` / `adjust-endpoint` (modify existing) — when the user needs to build or modify a pipeline before deploying
- **data-exploration** → `build-notebook` — when the user wants to create marimo notebooks to deploy as interactive jobs
- **performance** → `optimize-performance` — when a deployed job is slow, OOM-killed, or hitting its timeout, *before* proposing a bigger instance size or a longer `execute.timeout`; those spend run-time budget on every run, so tune first (install if absent: `uv run dlthub --non-interactive ai toolkit install performance`)

### Incoming (to dlthub-platform)

- From **rest-api-pipeline** (after `debug-pipeline` or hardening steps) — pipeline name, destination, and dataset are already known; carry them into `setup-runtime` and `deploy-workspace` without re-discovery
- From **sql-database-pipeline** (after `create-sql-database-pipeline`, `debug-sql-database-pipeline`, `adjust-table`, or `add-table`) — pipeline name, destination, and dataset are already known; carry them into `setup-runtime` and `deploy-workspace` without re-discovery
- From **filesystem-pipeline** (after `create-filesystem-pipeline` or `add-incremental-loading`) — pipeline name, destination, and dataset are already known; carry them into `setup-runtime` without re-discovery
- From **transformations** (after `create-transformation` or `debug-transformation`) — transformation scripts and pipeline destination are already known; carry them into `setup-runtime`
- From **data-exploration** (after `build-notebook`) — notebook file already exists; `deploy-workspace` should use `dlthub serve` for the notebook job
- From **data-quality** Profile A (after `run-data-quality`) — pipeline script with embedded `@dq.with_checks` decorators is the deployment target; carry the pipeline script path, pipeline name, and destination into `setup-runtime`
- From **data-quality** Profile B (after `run-data-quality`) — the data quality script that `run-data-quality` wrote already exists with confirmed checks; carry the script path, pipeline name, and destination into `setup-runtime` as the deployment target
- From **performance** (after `optimize-performance`, when the pipeline is tuned and the runner is the ceiling) — the bottleneck is diagnosed. Follow `instance-sizing.md` in (`deploy-workspace`) and the `job-resources` rule: the budget math, the user's explicit yes, then `require={"instance": {"size": ...}}` and `dlthub deploy`. Without that approval, route back to `optimize-performance`.
- From **quick-start** (Production path, or a shortcut when a working pipeline exists) — pipeline name and destination may be inferred from `dlthub ai status`; `setup-runtime` runs full discovery if not.

References:
* **Additional documentation** https://dlthub.com/docs/hub/llms.txt
* **Workspace deployment reference**: https://dlthub.com/docs/hub/pipeline-operations/deployments.md
* **Runtime overview**: https://dlthub.com/docs/hub/pipeline-operations/overview.md
* **Background agents**: https://dlthub.com/docs/hub/agents/agent-definitions.md

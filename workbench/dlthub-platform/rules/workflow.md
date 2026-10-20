# Deploy to dltHub Platform

## Workflow Entry
**ALWAYS** start with **Setup runtime** (`setup-runtime`) — ensure workspace, dependencies, and runtime login are ready

## Core workflow
1. **Prepare workspace** (`prepare-deployment`) — split dev/prod credentials, set up production destination
2. **Deploy pipeline** (`deploy-workspace`) — prepare scripts for production, simulate job runs locally (`dlthub local run`/`serve`), deploy, launch, schedule

## Extend and harden
3. **Debug deployment** (`debug-deployment`) — check job status, view logs, diagnose failures
4. **Inspect failures unattended** (`job-inspector`) — background agent: runs after a job fails, reads the run record and the logs, follows the traceback into the workspace code, classifies the failure and proposes a fix naming the target and the change. Declare it with `run.agent("dlthub-platform:job-inspector", trigger=..., require={"profile": "access"})`, and set `AGENT__MODEL` in the workspace, at least as capable as Claude Sonnet 5. "Background agents" in (`deploy-workspace`) `advanced-patterns.md` says why each of those matters
5. **Watch upstream API changes unattended** (`api-change-monitor`) — background agent: on a schedule, finds the APIs the code in `__deployment__.py` calls (or takes them from its `apis` input), reads each one's release notes, maps every breaking change, deprecation, enhancement and new endpoint to the pipeline resources and downstream models it touches, and recommends the edit. Shopify, Stripe, GitHub, HubSpot, Zendesk, Salesforce, Pipedrive, Google Ads, Jira, Amazon SP-API and NetSuite have built-in sources; another API takes `name=<release notes url>` in `apis`, or the agent searches for it. Declare one job for all APIs: decorate `async def api_change_monitor(run_context=None, apis="", since="", reviewed_versions="") -> dict` with `@run.agent(agent="dlthub-platform:api-change-monitor", trigger="schedule:0 7 * * 1", require={"profile": "access"})` and return `await monitor.run_per_api(run_context, apis=apis, since=since, reviewed_versions=reviewed_versions)`, where `monitor = load_agent_module(".claude/dlthub/agents/dlthub-platform/api-change-monitor")` from `dlt._workspace.deployment.agent.manifest`. The job runs the model once per API that has notes left after its script ruled the rest out, and merges the runs into one report and table, so an API with nothing new costs no tokens. Set `AGENT__MODEL`, at least as capable as Claude Sonnet 5. Apply what it recommends in **rest-api-pipeline** with `adjust-endpoint` and `new-endpoint`
6. **Add an API's release notes source** (`add-api-change-source`) — when the `api-change-monitor` report says an API's release notes were unknown, not found, guessed or found by search, or lists a coverage gap: find the official changelog, prove the agent's reader can date it, and save it as a `[api_change_monitor.sources.<name>]` entry in `.dlt/config.toml`, which the agent reads before any guess or search

## Handover to other toolkits

### Outgoing (from dlthub-platform)

- **rest-api-pipeline** → `debug-pipeline` / `adjust-endpoint` (modify existing) — when the user needs to build or modify a pipeline before deploying
- **data-exploration** → `build-notebook` — when the user wants to create marimo notebooks to deploy as interactive jobs
- **performance** → `optimize-performance` — when a deployed job is slow, OOM-killed, or hitting its timeout, *before* proposing a bigger instance size or a longer `execute.timeout`; those spend run-time budget on every run, so tune first (install if absent: `uv run dlthub --non-interactive ai toolkit install performance`)

### Incoming (to dlthub-platform)

- From **rest-api-pipeline** (after `debug-pipeline` or hardening steps) — pipeline name, destination, and dataset are already known; carry them into `setup-runtime` and `deploy-workspace` without re-discovery
- From **sql-database-pipeline** (after `create-sql-database-pipeline`, `debug-pipeline`, `adjust-table`, or `add-table`) — pipeline name, destination, and dataset are already known; carry them into `setup-runtime` and `deploy-workspace` without re-discovery
- From **filesystem-pipeline** (after `create-filesystem-pipeline` or `add-incremental-loading`) — pipeline name, destination, and dataset are already known; carry them into `setup-runtime` without re-discovery
- From **transformations** (after `create-transformation` or `debug-transformation`) — transformation scripts and pipeline destination are already known; carry them into `setup-runtime`
- From **data-exploration** (after `build-notebook`) — notebook file already exists; `deploy-workspace` should use `dlthub serve` for the notebook job
- From **data-quality** Profile A (after `run-data-quality`) — pipeline script with embedded `@dq.with_checks` decorators is the deployment target; carry the pipeline script path, pipeline name, and destination into `setup-runtime`
- From **data-quality** Profile B (after `run-data-quality`) — `tools/dq_run.py` already exists with confirmed checks; carry the script path, pipeline name, and destination into `setup-runtime` as the deployment target
- From **performance** (after `optimize-performance` Step 4, with the user's explicit approval and budget math) — the bottleneck is diagnosed and the tier bump is agreed; apply `require={"instance": {"size": ...}}` in the manifest and `dlthub deploy`. Without that approval, route back to `optimize-performance`.
- From **quick-start** (shortcut path when a working pipeline exists) — pipeline name and destination may be inferred from `dlthub ai status`; `setup-runtime` runs full discovery if not.

References:
* **Additional documentation** https://dlthub.com/docs/hub/llms.txt
* **Workspace deployment reference**: https://dlthub.com/docs/hub/pipeline-operations/deployments.md
* **Runtime overview**: https://dlthub.com/docs/hub/pipeline-operations/overview.md

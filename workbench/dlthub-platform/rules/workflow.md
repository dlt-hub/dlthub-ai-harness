# Deploy to dltHub Platform

## Workflow Entry
**ALWAYS** start with **Setup runtime** (`setup-runtime`) — ensure workspace, dependencies, and runtime login are ready

## Core workflow
1. **Prepare workspace** (`prepare-deployment`) — split dev/prod credentials, set up production destination
2. **Deploy pipeline** (`deploy-workspace`) — prepare scripts for production, simulate job runs locally (`dlthub local run`/`serve`), deploy, launch, schedule

## Extend and harden
3. **Debug deployment** (`debug-deployment`) — check job status, view logs, diagnose failures

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
* **Platform tutorial**: https://dlthub.com/docs/hub/getting-started/platform-tutorial.md

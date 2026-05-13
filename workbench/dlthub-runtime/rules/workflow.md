# Deploy to dltHub Runtime

## Workflow Entry
**ALWAYS** start with **Setup runtime** (`setup-runtime`) — ensure workspace, dependencies, and runtime login are ready

## Core workflow
1. **Prepare workspace** (`prepare-deployment`) — split dev/prod credentials, set up production destination
2. **Deploy pipeline** (`deploy-workspace`) — prepare scripts for production, deploy, launch, schedule

## Extend and harden
3. **Debug deployment** (`debug-deployment`) — check job status, view logs, diagnose failures

## Handover to other toolkits

### Outgoing (from dlthub-runtime)

- **rest-api-pipeline** → `debug-pipeline` / `adjust-endpoint` (modify existing) — when the user needs to build or modify a pipeline before deploying
- **data-exploration** → `build-notebook` — when the user wants to create marimo notebooks to deploy as interactive jobs

### Incoming (to dlthub-runtime)

- From **rest-api-pipeline** (after `debug-pipeline` or hardening steps) — pipeline name, destination, and dataset are already known; carry them into `setup-runtime` and `deploy-workspace` without re-discovery
- From **sql-database-pipeline** (after `create-sql-database-pipeline`, `debug-pipeline`, `adjust-table`, or `add-table`) — pipeline name, destination, and dataset are already known; carry them into `setup-runtime` and `deploy-workspace` without re-discovery
- From **filesystem-pipeline** (after `create-filesystem-pipeline` or `add-incremental-loading`) — pipeline name, destination, and dataset are already known; carry them into `setup-runtime` without re-discovery
- From **transformations** (after `create-transformation`) — transformation scripts and pipeline destination are already known; carry them into `setup-runtime`
- From **data-exploration** (after `build-notebook`) — notebook file already exists; `deploy-workspace` should use `dlt runtime serve` for the notebook job
- From **data-quality** Profile A (after `run-data-quality`) — pipeline script with embedded `@dq.with_checks` decorators is the deployment target; carry the pipeline script path, pipeline name, and destination into `setup-runtime`
- From **data-quality** Profile B (after `run-data-quality`) — `tools/dq_run.py` already exists with confirmed checks; carry the script path, pipeline name, and destination into `setup-runtime` as the deployment target

References:
* **Additional documentation** https://dlthub.com/docs/hub/llms.txt
* **Workspace deployment reference**: https://raw.githubusercontent.com/dlt-hub/runtime-starter-pack/refs/heads/main/REFERENCE.md
  <!-- TODO: replace with stable docs URL when official runtime docs are published -->
* **Runtime overview**: https://feat-workspace-deployment-2-docs.services4758.workers.dev/docs/devel/hub/runtime/overview.md
  <!-- TODO: replace with stable docs URL when official runtime docs are published -->

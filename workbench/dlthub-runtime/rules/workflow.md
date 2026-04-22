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

- **rest-api-pipeline** — when the user needs to build or modify a pipeline before deploying
- **data-exploration** — when the user wants to create marimo notebooks to deploy as interactive jobs

### Incoming (to dlthub-runtime)

- From **rest-api-pipeline** (after `debug-pipeline` or hardening steps) — pipeline name, destination, and dataset are already known; carry them into `setup-runtime` and `deploy-workspace` without re-discovery
- From **transformations** (after `create-transformation`) — transformation scripts and pipeline destination are already known; carry them into `setup-runtime`
- From **data-exploration** (after `build-notebook`) — notebook file already exists; `deploy-workspace` should use `dlt runtime serve` for the notebook job
- From **data-quality** (after `run-data-quality`) — `tools/dq_run.py` already exists with confirmed checks; carry the script path, pipeline name, and destination into `setup-runtime` as the deployment target

References:
* **Additional documentation** https://dlthub.com/docs/hub/llms.txt
* **Workspace and runtime CLI** https://dlthub.com/docs/hub/command-line-interface.md
* **Runtime overview** https://dlthub.com/docs/hub/runtime/overview.md

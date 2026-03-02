# Deploy to dltHub Runtime

## Workflow Entry
**ALWAYS** start with **Setup runtime** (`setup-runtime`) — ensure workspace, dependencies, and runtime login are ready

## Core workflow
1. **Prepare workspace** (`prepare-deployment`) — split dev/prod credentials, set up production destination
2. **Deploy pipeline** (`deploy-workspace`) — prepare scripts for production, deploy, launch, schedule

## Extend and harden
3. **Debug deployment** (`debug-deployment`) — check job status, view logs, diagnose failures

## Handover to other toolkits

When the user's needs go beyond this toolkit, hand over to:

- **rest-api-pipeline** — when the user needs to build or modify a pipeline before deploying
- **data-exploration** — when the user wants to create marimo notebooks to deploy as interactive jobs

References:
* **Additional documentation** https://dlthub.com/docs/hub/llms.txt
* **Workspace and runtime CLI** https://dlthub.com/docs/hub/command-line-interface.md
* **Runtime overview** https://dlthub.com/docs/hub/runtime/overview.md

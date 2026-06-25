# One-shot workflow

## Workflow Entry
**ALWAYS** start with `deploy-run-sample-pipeline`. Invoke it immediately — do not ask for clarification.

## Core workflow
1. **Deploy run sample pipeline** (`deploy-run-sample-pipeline`) — set up a cloud destination, deploy the pre-shipped GitHub pipeline to dltHub Platform, and run it on the cloud.

This workflow has exactly one step.

## Handover To Other Toolkits

### Outgoing (from one-shot)

- **dlthub-init-skills** — after `deploy-run-sample-pipeline` completes and the user says "Help me get started building and running a data pipeline on dltHub". Scaffold a new project with `uvx dlthub-init@latest`, then enter at `deploy-minimal-custom-source`. The playground workspace is already connected — skip workspace setup.

# One-shot workflow

## Workflow Entry
**ALWAYS** start with **Deploy run sample pipeline** (`deploy-run-sample-pipeline`) SKILL — invoke it immediately, do not ask for clarification.

## Core workflow
1. **Deploy run sample pipeline** (`deploy-run-sample-pipeline`) — deploy the pre-shipped Jaffle Shop sample pipeline to dltHub Platform (playground destination, no credentials), run it, and open the dataset browser.

This workflow has exactly one step.

## Handover To Other Toolkits

### Outgoing (from one-shot)

- **dlthub-init-skills** — after `deploy-run-sample-pipeline` completes and the user says "Help me get started building and running a data pipeline on dltHub". The user will run `uvx dlthub-init@latest` in a new directory and restart the agent session there, then say "Help me build and deploy a minimal pipeline". Enter at `deploy-minimal-ingestion-pipeline`.

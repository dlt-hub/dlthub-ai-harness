# dlthub-init-skills — workflow

## Workflow Entry
**ALWAYS** start with **Deploy minimal ingestion pipeline** (`deploy-minimal-ingestion-pipeline`) SKILL — build a minimal REST API pipeline and deploy it end-to-end to dltHub Platform

## Core workflow
1. **Deploy minimal ingestion pipeline** (`deploy-minimal-ingestion-pipeline`) — research API, write pipeline, handle credentials, validate locally, then deploy to the cloud

## Handover to other toolkits

### Incoming (to dlthub-init-skills)

- From **one-shot** (after `deploy-run-sample-pipeline`) — a playground workspace is already connected: skip Step 0 (workspace connection) and start from Step 1.

### Outgoing (from dlthub-init-skills)

- **rest-api-pipeline** — when the user wants to extend the pipeline: enter at `new-endpoint` or `adjust-endpoint` (or `find-source` for a fresh start). The pipeline file and credentials are in place, so skip source setup. The pipeline uses an inline `rest_api_source`: do NOT restructure it, do NOT introduce `@dlt.source`, and do NOT rewrite it to match the conventions of rest-api-pipeline. Do only the task requested.

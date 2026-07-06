# dlthub-init-skills — workflow

## Workflow Entry
**ALWAYS** start with **Deploy minimal ingestion pipeline** (`deploy-minimal-ingestion-pipeline`) SKILL — build a minimal REST API pipeline and deploy it end-to-end to dltHub Platform

## Core workflow
1. **Deploy minimal ingestion pipeline** (`deploy-minimal-ingestion-pipeline`) — research API, write pipeline, handle credentials, validate locally, then deploy to the cloud

## Handover to other toolkits

### Incoming (to dlthub-init-skills)

- From **one-shot** (after `deploy-run-sample-pipeline`) — the user has just completed onboarding with the sample pipeline in the same environment. A playground workspace is already connected. Skip Step 0 (workspace connection) and start from Step 1.

### Outgoing (from dlthub-init-skills)

- **rest-api-pipeline** — after `deploy-minimal-ingestion-pipeline` completes and the user says "Help me extend my pipeline". Enter at `new-endpoint` (to add more endpoints), `adjust-endpoint` (to add incremental loading or pagination), or `find-source` (for a fresh start with the full toolkit). The pipeline file and credentials are already in place — skip source setup.

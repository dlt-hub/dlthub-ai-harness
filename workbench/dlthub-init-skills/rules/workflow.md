# dlthub-init-skills — workflow

## Workflow Entry
**ALWAYS** start with **Deploy minimal custom source** (`deploy-minimal-custom-source`) SKILL — build a minimal REST API pipeline and deploy it end-to-end to dltHub Platform

## Core workflow
1. **Deploy minimal custom source** (`deploy-minimal-custom-source`) — research API, write pipeline, handle credentials, validate locally, then deploy to the cloud

## Handover to other toolkits

### Incoming (to dlthub-init-skills)

- From **one-shot** (after `deploy-run-sample-pipeline`) — the user has just completed onboarding with the sample pipeline in the same environment. A playground workspace is already connected. Skip workspace connection (Step 5) and go straight to Step 6 (production destination setup).

### Outgoing (from dlthub-init-skills)

- **rest-api-pipeline** — after the minimal pipeline is working and deployed, when the user wants to add more endpoints, pagination, incremental loading, or production-grade hardening. Enter at `find-source` with the source name already known — skip the discovery question.
- **dlthub-platform** — if the user wants to schedule or manage the deployed pipeline beyond the initial run. Enter at `setup-runtime`.

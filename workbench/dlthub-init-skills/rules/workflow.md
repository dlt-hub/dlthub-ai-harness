# dlthub-init-skills — workflow

## Workflow Entry
**ALWAYS** start with **Deploy minimal custom source** (`deploy-minimal-custom-source`) SKILL — build a minimal REST API pipeline and deploy it end-to-end to dltHub Platform

## Core workflow
1. **Deploy minimal custom source** (`deploy-minimal-custom-source`) — research API, write pipeline, handle credentials, validate locally, then deploy to the cloud

## Handover to other toolkits

### Incoming (to dlthub-init-skills)

- From **one-shot** (after `deploy-run-sample-pipeline`) — the user has just completed onboarding with the sample pipeline in the same environment. A playground workspace is already connected. Skip workspace connection (Step 5) and go straight to Step 6 (production destination setup).

### Outgoing (from dlthub-init-skills)

This toolkit ends when the pipeline is deployed. It does not hand off to other toolkits — this workspace is a minimal test environment and is not meant to be extended. When the user wants to build a real pipeline, direct them to run `uvx dlthub-init@latest <dir>` in a new directory.

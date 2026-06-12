# One-shot workflow

## Workflow Entry
**ALWAYS** start with **Create minimal pipeline** (`create-minimal-pipeline`) — research the API, scaffold a pipeline, configure auth, and run locally with a 50-row limit.

When the user sends **"Build a dlt pipeline for [your data source] API and load data from [your endpoint] into DuckDB"** — even if the placeholders are literally unfilled — invoke `create-minimal-pipeline` immediately. Do **not** ask for clarification inline. The skill's Step 0 handles the no-source case.

## Core workflow
1. **Create minimal pipeline** (`create-minimal-pipeline`) — research API, scaffold pipeline, configure auth, run locally with a 50-row limit
2. **Deploy minimal pipeline** (`deploy-minimal-pipeline`) — set up production destination, deploy the pipeline to dltHub Platform, and verify it runs on the cloud

## Handover to other toolkits

### Outgoing (from one-shot)
- **data-exploration** — after both `create-minimal-pipeline` and `deploy-minimal-pipeline` complete successfully: offer "your data is live — want to explore it with charts and notebooks?". Run `uv run dlthub --non-interactive ai toolkit install data-exploration`, then invoke `explore-data`.
- **rest-api-pipeline** — run `uv run dlthub --non-interactive ai toolkit install rest-api-pipeline` first, then pick the entry point:
  - *Pagination / incremental loading / remove the 50-row limit*: invoke `adjust-endpoint`.
  - *Add more endpoints*: invoke `new-endpoint`.
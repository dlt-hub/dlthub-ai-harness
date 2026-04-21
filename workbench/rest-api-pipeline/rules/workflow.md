# New ingestion pipeline

## Workflow Entry
**ALWAYS** start with **Find source** (`find-source`) SKILL — discover the right dlt source for the user's data provider

## Core workflow
1. **Create pipeline** (`create-rest-api-pipeline`) — scaffold, write code, configure credentials
2. **Debug pipeline** (`debug-pipeline`) — run it, inspect traces and load packages, fix errors
3. **Validate data** (`validate-data`) — inspect schema and data, fix types and structures, iterate until user is satisfied

## Extend and harden

4. **Deploy to runtime** — hand off to **dlthub-runtime** to deploy and run the pipeline on dltHub; can be done with a working pipeline
5. **Adjust endpoint** (`adjust-endpoint`) — add pagination, remove limits, add hints, mappings, correct schema etc.
6. **Add incremental loading** — set up `dlt.sources.incremental`, merge keys, and lag windows for production efficiency
7. **Add endpoints** (`new-endpoint`) — add more resources to the source
8. **View data** (`view-data`) — show data to the user & query and explore loaded data in Python

## Handover to other toolkits

### Incoming (to rest-api-pipeline)

- From **dlthub-runtime** (from `deploy-workspace` when the pipeline needs modification before deploying) — pipeline name and destination are already known; skip `find-source` discovery and go straight to the relevant fix skill (`debug-pipeline`, `adjust-endpoint`, or `new-endpoint`).

### Outgoing (from rest-api-pipeline)

When the user's needs go beyond this toolkit, hand over to:

- **data-exploration** — after `validate-data` or `view-data`, when the user wants interactive notebooks, charts, dashboards, or deeper analysis with marimo
- **transformations** — after `validate-data` or `view-data`, when the user wants to model the ingested data into a CDM or run cross-source transformations
- **dlthub-runtime** — two entry points:
  - **Early** (after `create-rest-api-pipeline` or `debug-pipeline`): when the user wants to run the pipeline on dltHub right away — a working pipeline is enough to deploy
  - **Later** (after `adjust-endpoint`, incremental loading, `add-endpoints`, or a subsequent `debug-pipeline` run): when the pipeline is refined and the user wants to deploy or schedule it on dltHub

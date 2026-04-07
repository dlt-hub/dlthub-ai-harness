# New ingestion pipeline

## Workflow Entry
**ALWAYS** start with **Find source** (`find-source`) SKILL — discover the right dlt source for the user's data provider

## Core workflow
1. **Create pipeline** (`create-rest-api-pipeline`) — scaffold, write code, configure credentials
2. **Debug pipeline** (`debug-pipeline`) — run it, inspect traces and load packages, fix errors
3. **Validate data** (`validate-data`) — inspect schema and data, fix types and structures, iterate until user is satisfied

## Extend and harden

4. **Adjust endpoint** (`adjust-endpoint`) — add pagination, remove limits, add hints, mappings, correct schema etc.
5. **Add incremental loading** — set up `dlt.sources.incremental`, merge keys, and lag windows for production efficiency
6. **Add endpoints** (`new-endpoint`) — add more resources to the source
7. **View data** (`view-data`) — show data to the user & query and explore loaded data in Python

## Handover to other toolkits

When the user's needs go beyond this toolkit, hand over to:

- **data-exploration** — after `validate-data` or `view-data`, when the user wants interactive notebooks, charts, dashboards, or deeper analysis with marimo
- **transformations** — after `validate-data` or `view-data`, when the user wants to model the ingested data into a CDM or run cross-source transformations
- **dlthub-runtime** — when the pipeline is production-ready and the user wants to deploy, schedule, or run it on the dltHub platform

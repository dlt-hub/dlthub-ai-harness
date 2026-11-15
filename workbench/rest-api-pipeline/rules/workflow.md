# New ingestion pipeline

## Workflow Entry
**ALWAYS** start with **Find source** (`find-source`) SKILL — discover the right dlt source for the user's data provider

## Core workflow
1. **Create pipeline** (`create-rest-api-pipeline`) — scaffold, write code, configure credentials. For a verified source, `find-source` (step 8) scaffolds it with `dlthub pipeline init` instead, then continue at **Debug pipeline**
2. **Debug pipeline** (`debug-pipeline`) — run it, inspect traces and load packages, fix errors
3. **Validate data** (`validate-data`) — inspect schema and data, fix types and structures, iterate until user is satisfied

## Extend and harden

4. **Adjust endpoint** (`adjust-endpoint`) — add pagination, remove limits, add hints, mappings, correct schema etc.
5. **Add incremental loading** (`adjust-endpoint`) — set up `dlt.sources.incremental`, merge keys, and lag windows for production efficiency
6. **Add endpoints** (`new-endpoint`) — add more resources to the source
7. **View data** (`view-data`) — show data to the user & query and explore loaded data in Python
8. **Optimize performance** (`optimize-rest-api-performance`) — when the pipeline works but is slow: parallelize child resources, raise page size, run resources concurrently, tune retries

## Handover to other toolkits

### Outgoing (from rest-api-pipeline)

When the user's needs go beyond this toolkit, hand over to:

- **data-exploration** — after `validate-data` or `view-data`, when the user wants interactive notebooks, charts, dashboards, or deeper analysis with marimo
- **transformations** — after `validate-data` or `view-data`, when the user wants to model the ingested data into a CDM or run cross-source transformations
- **data-quality** — after `validate-data`, when the user wants ongoing validation, check contracts, or quality guarantees on every pipeline load
- **filesystem-pipeline** — from (`find-source`) when the user's data source is file-based (S3, GCS, local CSV, SFTP, etc.) rather than a REST API
- **sql-database-pipeline** — from (`find-source`) when the user's data source is a SQL database (Postgres, MySQL, MS SQL, Oracle, etc.) rather than a REST API; start at `find-sql-database-source`
- **performance** — after `optimize-rest-api-performance`, when the pipeline works but is slow or memory-heavy and needs source-agnostic stage tuning (extract/normalize/load workers, buffers, file rotation); start at `optimize-performance`
- a platform toolkit — when the user wants to deploy, schedule or run the jobs in production: follow the workflow entry of the installed platform toolkit, carrying the pipeline name, destination and dataset. When none is installed, `dlthub-router` installs one. A working pipeline is enough (after `debug-pipeline`); a hardened one (incremental loading, no dev limits) is better for a schedule

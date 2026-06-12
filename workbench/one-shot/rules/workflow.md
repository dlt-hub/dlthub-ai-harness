# One-shot workflow

## Workflow Entry
**ALWAYS** start with **Create minimal pipeline** (`create-minimal-pipeline`) — research the API, scaffold a pipeline, configure auth, and run locally with a 50-row limit.

When the user sends **"Build a dlt pipeline for [your data source] API and load data from [your endpoint] into DuckDB"** — even if the placeholders are literally unfilled — invoke `create-minimal-pipeline` immediately. Do **not** ask for clarification inline. The skill's Step 0 handles the no-source case.

## Core workflow
1. **Create minimal pipeline** (`create-minimal-pipeline`) — research API, scaffold pipeline, configure auth, run locally with a 50-row limit
2. **Deploy minimal pipeline** (`deploy-minimal-pipeline`) — set up production destination, deploy the pipeline to dltHub Platform, and verify it runs on the cloud

## Handover to other toolkits

### Outgoing (from one-shot)
- **sql-database-pipeline** — when the user's source is a SQL or relational database (Postgres, MySQL, BigQuery, etc.): run `uv run dlthub --non-interactive ai toolkit install sql-database-pipeline`, then invoke `find-source`.
- **filesystem-pipeline** — when the user's source is files or object storage (S3, GCS, Azure, CSV, Parquet, SFTP, etc.): run `uv run dlthub --non-interactive ai toolkit install filesystem-pipeline`, then invoke `create-filesystem-pipeline`.
- **rest-api-pipeline** — run `uv run dlthub --non-interactive ai toolkit install rest-api-pipeline` first, then pick the entry point:
  - *Cloud destination*: after `dlthub local show` succeeds, offer "your data is in DuckDB — want to try loading to a cloud destination?". If yes, change `destination="duckdb"` to the chosen destination, set up destination credentials, re-run. Invoke `debug-pipeline`.
  - *Pagination / incremental loading / remove the 50-row limit*: invoke `adjust-endpoint`.
  - *Add more endpoints*: invoke `new-endpoint`.
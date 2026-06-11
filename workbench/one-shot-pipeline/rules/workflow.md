# One-shot pipeline workflow

## Core workflow
1. **One-shot pipeline** (`one-shot-pipeline`) — research API, scaffold pipeline, configure auth, run locally with a 50-row limit

## Handover to other toolkits

### Outgoing (from one-shot-pipeline)
- **sql-database-pipeline** — from (`one-shot-pipeline`), when the user's source is a SQL or relational database (Postgres, MySQL, BigQuery, etc.); start at `find-source`
- **filesystem-pipeline** — from (`one-shot-pipeline`), when the user's source is files or object storage (S3, GCS, Azure, CSV, Parquet, SFTP, etc.); start at `create-filesystem-pipeline`
- **rest-api-pipeline** — from (`one-shot-pipeline`), three triggers, each with a specific entry point:
  - *Cloud destination*: after `dlthub local show` succeeds, offer "your data is in DuckDB — want to try loading to a cloud destination?". If yes, change `destination="duckdb"` to the chosen destination, set up destination credentials, re-run. Enter at `debug-pipeline`.
  - *Pagination / incremental loading / remove the 50-row limit*: enter at `adjust-endpoint`.
  - *Add more endpoints*: enter at `new-endpoint`.
# One-shot pipeline workflow

## Core workflow
1. **One-shot pipeline** (`one-shot-pipeline`) — research API, scaffold pipeline, configure auth, run locally with a 50-row limit

## Handover to other toolkits

### Outgoing (from one-shot-pipeline)
- **sql-database-pipeline** — when the user's source is a SQL or relational database (Postgres, MySQL, BigQuery, etc.): run `uv run dlthub --non-interactive ai toolkit install sql-database-pipeline`, then invoke `find-source`.
- **filesystem-pipeline** — when the user's source is files or object storage (S3, GCS, Azure, CSV, Parquet, SFTP, etc.): run `uv run dlthub --non-interactive ai toolkit install filesystem-pipeline`, then invoke `create-filesystem-pipeline`.
- **rest-api-pipeline** — run `uv run dlthub --non-interactive ai toolkit install rest-api-pipeline` first, then pick the entry point:
  - *Cloud destination*: after `dlthub local show` succeeds, offer "your data is in DuckDB — want to try loading to a cloud destination?". If yes, change `destination="duckdb"` to the chosen destination, set up destination credentials, re-run. Invoke `debug-pipeline`.
  - *Pagination / incremental loading / remove the 50-row limit*: invoke `adjust-endpoint`.
  - *Add more endpoints*: invoke `new-endpoint`.
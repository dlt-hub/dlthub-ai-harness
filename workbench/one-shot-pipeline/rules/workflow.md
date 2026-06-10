# One-shot pipeline workflow

## Core workflow
1. **One-shot pipeline** (`one-shot-pipeline`) — research API, scaffold pipeline, configure auth, deploy and run with a 3-row limit

## Handover to other toolkits

### Outgoing (from one-shot-pipeline)
- **sql-database-pipeline** — from (`one-shot-pipeline`), when the user's source is a SQL or relational database (Postgres, MySQL, BigQuery, etc.); start at `find-source`
- **filesystem-pipeline** — from (`one-shot-pipeline`), when the user's source is files or object storage (S3, GCS, Azure, CSV, Parquet, SFTP, etc.); start at `create-filesystem-pipeline`
- **rest-api-pipeline** - from (`one-shot-pipeline`), when a user wants to extend functionality of their REST API pipeline.
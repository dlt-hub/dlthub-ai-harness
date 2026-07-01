---
name: sql-database-pipeline
description: Build a dlt pipeline that loads tables from a SQL database — Postgres,
  MySQL, SQL Server, Snowflake, BigQuery, or any database dlt's sql_database source
  supports. Use when the user wants to replicate or ingest database tables into a
  destination. DO NOT USE for REST/HTTP APIs (use rest-api-pipeline) or files exported
  from a database (use filesystem-pipeline).
---

Your identity and guardrails (SOUL) are already loaded via the `init` base toolkit — operate from them, especially on secrets, sampling, and running from the project root.

## Before you start

Requires a dlthub workspace. Verify with `uv run dlthub ai status`. If the
workspace or dlt isn't set up, help the user initialize one before continuing.

For dlt itself: read https://dlthub.com/docs/llms.txt and follow it to the
SQL database source — https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database

## Workflow

### Step 1 — Find the source and pick tables
Classify the database type, explore its schemas and tables, gather connection details, and pick the first table(s) and destination to load.
→ Docs: https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/setup.md
✓ Done when: the database type is known, connection details are gathered, and the user has chosen which tables to load.

### Step 2 — Scaffold and configure credentials
Scaffold the `sql_database` source, set up the connection string via the workspace secrets tools, and choose the extraction backend.
→ Docs: https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/configuration.md
✓ Done when: a pipeline run connects to the database without a credentials or driver error.

### Step 3 — Run on a sample
Run with a row limit or a single small table to validate the output and column types before a full load.
→ Docs: https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/usage
✓ Done when: the pipeline completes without errors and the sample table loads with the expected schema.

### Step 4 — Inspect and confirm
Show the user the loaded tables, row counts, and schema. Fix column types and mappings, and get confirmation before proceeding.
→ Docs: https://dlthub.com/docs/general-usage/dataset-access/dataset.md
✓ Done when: the user confirms the data and types look correct.

### Step 5 — Run full load
Remove dev limits and run the full load. Add incremental loading with a cursor column and configure merge keys where the source supports it.
→ Docs: https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/configuration#incremental-loading
✓ Done when: a full run completes and row counts match expectations.

## What's next

- Data loaded successfully → the pipeline is ready for scheduling or transformation.
- User wants to explore the data → point them to the dlt dataset API (https://dlthub.com/docs/general-usage/dataset-access/dataset.md).
- User wants to schedule or deploy → outside this toolkit's scope (requires dltHub Platform).

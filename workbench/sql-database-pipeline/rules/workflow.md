# SQL database pipeline

## Workflow Entry
**ALWAYS** start with **Find source** (`find-source`) SKILL — identify the database, explore available tables, and pick what to load

## Core workflow
1. **Find source** (`find-source`) — classify the database type, explore schemas and tables, gather connection details, pick first table and destination
2. **Create pipeline** (`create-sql-database-pipeline`) — scaffold with `dlt init sql_database`, write code, set up credentials, test load, choose backend
3. **Debug pipeline** (`debug-pipeline`) — run it, inspect traces and load packages, fix connection or driver errors
4. **Validate data** (`validate-data`) — inspect schema and data, fix types and column mappings, iterate until correct

## Extend and harden

1. **Deploy to runtime** — hand off to **dlthub-runtime** to deploy and run the pipeline on dltHub; can be done with a working pipeline
2. **Adjust table** (`adjust-table`) — remove dev limits, fix column types, add hints and mappings, correct schema
3. **Add incremental loading** — set up cursor column for incremental loads, merge keys for deduplication, and write disposition for production efficiency
4. **Add tables** (`add-table`) — add more tables or views from the same database into the pipeline
5. **Transform before loading** — use `query_adapter_callback` to filter rows at SQL level, `table_adapter_callback` to modify schema, or `add_map` to transform rows after extraction; see `create-sql-database-pipeline` step 7
6. **View data** — query and explore loaded data in Python or DuckDB

## Handover to other toolkits

### Incoming (to sql-database-pipeline)

- From **dlthub-runtime** (from `deploy-workspace` when the pipeline needs modification before deploying) — pipeline name and destination are already known; skip `find-source` discovery and go straight to the relevant fix skill (`debug-pipeline`, `adjust-table`, or `add-table`).

### Outgoing (from sql-database-pipeline)

When the user's needs go beyond this toolkit, hand over to:

- **data-exploration** — after `validate-data` or `view-data`, when the user wants interactive notebooks, charts, dashboards, or deeper analysis with marimo
- **transformations** — after `validate-data` or `view-data`, when the user wants to model the ingested data into a CDM or run cross-source transformations
- **data-quality** — after `validate-data`, when the user wants ongoing validation, check contracts, or quality guarantees on every pipeline load
- **dlthub-runtime** — two entry points:
  - **Early** (after `create-sql-database-pipeline` or `debug-pipeline`): when the user wants to run the pipeline on dltHub right away — a working pipeline is enough to deploy
  - **Later** (after `adjust-table`, incremental loading, `add-table`, or a subsequent `debug-pipeline` run): when the pipeline is refined and the user wants to deploy or schedule it on dltHub

# SQL database pipeline

## Workflow Entry
**ALWAYS** start with **Find source** (`find-source`) SKILL — identify the database, explore available tables, and pick what to load

## Core workflow
1. **Find source** (`find-source`) — classify the database type, explore schemas and tables, gather connection details, pick first table and destination
2. **Create pipeline** (`create-sql-database-pipeline`) — scaffold with `dlthub pipeline init sql_database`, write code, set up credentials, test load, choose backend
3. **Debug pipeline** (`debug-pipeline`) — run it, inspect traces and load packages, fix connection or driver errors
4. **Validate data** (`validate-data`) — inspect schema and data, fix types and column mappings, iterate until correct
5. **Clean up** — once the pipeline is working, remove temporary ad-hoc scripts (e.g. `explore_db.py`, `inspect_schema.py`, any throwaway `.py` files created during exploration). Keep only the pipeline script and config files.

## Extend and harden

1. **Deploy to dltHub Platform** — hand off to **dlthub-platform** to deploy and run the pipeline on dltHub; can be done with a working pipeline
2. **Adjust table** (`adjust-table`) — remove dev limits, add incremental loading with a cursor column, configure merge keys (for fixing column types/schema after a load, use `validate-data`)
3. **Add tables** (`add-table`) — add more tables or views from the same database into the pipeline
4. **Transform before loading** — use `query_adapter_callback` to filter rows at SQL level, `table_adapter_callback` to modify schema, or `add_map` to transform rows after extraction; see `create-sql-database-pipeline` — "Add transformation callbacks" section
5. **View data** (`view-data`) — query and explore loaded data using dlt dataset API, ibis, or raw SQL
6. **Optimize performance** (`optimize-sql-performance`) — when extraction is slow or memory-heavy: pick a faster backend, tune `chunk_size`, parallelize tables, reduce reflection, push filters to SQL

## Handover to other toolkits

### Incoming (to sql-database-pipeline)

- From **dlthub-platform** (from `deploy-workspace` when the pipeline needs modification before deploying) — pipeline name and destination are already known; skip `find-source` discovery and go straight to the relevant fix skill (`debug-pipeline`, `adjust-table`, or `add-table`).

### Outgoing (from sql-database-pipeline)

When the user's needs go beyond this toolkit, hand over to:

- **data-exploration** — after `validate-data` or `view-data`, when the user wants interactive notebooks, charts, dashboards, or deeper analysis with marimo
- **transformations** — after `validate-data` or `view-data`, when the user wants to model the ingested data into a CDM or run cross-source transformations
- **data-quality** — after `validate-data`, when the user wants ongoing validation, check contracts, or quality guarantees on every pipeline load
- **dlthub-platform** — two entry points:
  - **Early** (after `create-sql-database-pipeline` or `debug-pipeline`): when the user wants to run the pipeline on dltHub right away — a working pipeline is enough to deploy
  - **Later** (after `adjust-table`, incremental loading, `add-table`, or a subsequent `debug-pipeline` run): when the pipeline is refined and the user wants to deploy or schedule it on dltHub
- **performance** — after `optimize-sql-performance`, when the pipeline works but is slow or memory-heavy and needs source-agnostic stage tuning (extract/normalize/load workers, buffers, file rotation); start at `optimize-performance`

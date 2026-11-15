# SQL database pipeline

## Workflow Entry
**ALWAYS** start with **Find SQL database source** (`find-sql-database-source`) SKILL — identify the database, explore available tables, and pick what to load

## Core workflow
1. **Find SQL database source** (`find-sql-database-source`) — classify the database type, explore schemas and tables, gather connection details, pick first table and destination
2. **Create pipeline** (`create-sql-database-pipeline`) — scaffold with `dlthub pipeline init sql_database`, write code, set up credentials, test load, choose backend
3. **Debug pipeline** (`debug-sql-database-pipeline`) — run it, inspect traces and load packages, fix connection or driver errors
4. **Validate data** (`validate-sql-database-data`) — inspect schema and data, fix types and column mappings, iterate until correct
5. **Clean up** — ad-hoc exploration scripts live in the system temp dir, never in the workspace. If any were written to the workspace, remove them; keep only the pipeline script and config files.

## Extend and harden

1. **Deploy** — hand over to the installed platform toolkit to deploy and run the pipeline; can be done with a working pipeline
2. **Adjust table** (`adjust-table`) — remove dev limits, add incremental loading with a cursor column, configure merge keys (for fixing column types/schema after a load, use `validate-sql-database-data`)
3. **Add tables** (`add-table`) — add more tables or views from the same database into the pipeline
4. **Transform before loading** — use `query_adapter_callback` to filter rows at SQL level, `table_adapter_callback` to modify schema, or `add_map` to transform rows after extraction; see `create-sql-database-pipeline` — "Add transformation callbacks" section
5. **View data** (`view-sql-database-data`) — query and explore loaded data using dlt dataset API, ibis, or raw SQL
6. **Optimize performance** (`optimize-sql-performance`) — when extraction is slow or memory-heavy: pick a faster backend, tune `chunk_size`, parallelize tables, reduce reflection, push filters to SQL

## Handover to other toolkits

### Incoming (to sql-database-pipeline)

- From **rest-api-pipeline** (from `find-source`, when the user's data source turns out to be a SQL database) — start at `find-sql-database-source`; the database and destination may already be known.
- From a platform toolkit (when the pipeline needs modification before deploying) — pipeline name and destination are already known; skip `find-sql-database-source` discovery and go straight to the relevant fix skill (`debug-sql-database-pipeline`, `adjust-table`, or `add-table`).

### Outgoing (from sql-database-pipeline)

When the user's needs go beyond this toolkit, hand over to:

- **data-exploration** — after `validate-sql-database-data` or `view-sql-database-data`, when the user wants interactive notebooks, charts, dashboards, or deeper analysis with marimo
- **transformations** — after `validate-sql-database-data` or `view-sql-database-data`, when the user wants to model the ingested data into a CDM or run cross-source transformations
- **data-quality** — after `validate-sql-database-data`, when the user wants ongoing validation, check contracts, or quality guarantees on every pipeline load
- a platform toolkit — when the user wants to deploy, schedule or run the jobs in production: follow the workflow entry of the installed platform toolkit, carrying the pipeline name, destination and dataset. When none is installed, `dlthub-router` installs one. A working pipeline is enough (after `create-sql-database-pipeline` or `debug-sql-database-pipeline`); a refined one (after `adjust-table`, incremental loading or `add-table`) is better for a schedule
- **performance** — after `optimize-sql-performance`, when the pipeline works but is slow or memory-heavy and needs source-agnostic stage tuning (extract/normalize/load workers, buffers, file rotation); start at `optimize-performance`

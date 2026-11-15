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

6. **Adjust table** (`adjust-table`) — remove dev limits, add incremental loading with a cursor column, configure merge keys (for fixing column types/schema after a load, use `validate-sql-database-data`)
7. **Add tables** (`add-table`) — add more tables or views from the same database into the pipeline
8. **Transform before loading** — use `query_adapter_callback` to filter rows at SQL level, `table_adapter_callback` to modify schema, or `add_map` to transform rows after extraction; see `create-sql-database-pipeline` — "Add transformation callbacks" section
9. **View data** (`view-sql-database-data`) — query and explore loaded data using dlt dataset API, ibis, or raw SQL
10. **Optimize performance** (`optimize-sql-performance`) — when extraction is slow or memory-heavy: pick a faster backend, tune `chunk_size`, parallelize tables, reduce reflection, push filters to SQL

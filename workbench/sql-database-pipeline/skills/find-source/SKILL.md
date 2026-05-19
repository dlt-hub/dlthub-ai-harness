---
name: find-source
description: Find and explore a SQL database source for a dlt pipeline. Use when the user wants to load data from a relational database (postgres, mysql, mssql, oracle, sqlite, or any SQLAlchemy-supported database), mentions a database connection, wants to discover available tables, or asks to build a pipeline from a SQL source.
argument-hint: "[database-url-or-description] [destination]"
---

# Find a SQL database source

Identify the database, explore available tables, and choose what to load.

Parse `$ARGUMENTS`:
- `database` (required): description or connection URL of the source database (e.g. "postgres on localhost", "Rfam MySQL at rfam.org", a connection string, or just the DB type)
- `destination` (optional, default `duckdb`): where to load data

## Incoming context check

**Before running any steps**, check whether the pipeline already exists in this session:

- **Arriving from `dlthub-platform`** (e.g. the user was deploying and needs to fix the pipeline first) — pipeline name, destination, and loaded tables are already known. **Skip this skill entirely** and go directly to the relevant fix skill:
  - Pipeline errors or connection issues → `debug-pipeline`
  - Schema or column changes needed → `adjust-table`
  - Adding more tables → `add-table`

- **Arriving mid-session** with a pipeline already scaffolded — if a `*_pipeline.py` file exists and the user just wants to extend or fix it, skip steps 1–4 and go straight to step 5 to confirm tables and destination.

Only run the full discovery flow (steps 1–6) when starting fresh with no existing pipeline.

## Steps

### 1. Classify the database type

Map the user's description to a SQLAlchemy dialect + driver:

| Database | drivername | extra package |
|---|---|---|
| PostgreSQL | `postgresql+psycopg2` | `psycopg2-binary` |
| MySQL / MariaDB | `mysql+pymysql` | `pymysql` |
| MS SQL Server | `mssql+pyodbc` | `pyodbc` |
| Oracle | `oracle+cx_oracle` | `cx_Oracle` |
| SQLite | `sqlite` | _(built-in)_ |

If unclear, ask the user which database engine they are using.

### 2. Check intent and verified sources

Before assuming `sql_database` is the right tool, check what the user actually needs:

**STOP and hand off** if the use case matches a specialised verified source:

| User intent                                                                | Source | Docs |
|----------------------------------------------------------------------------| --- | --- |
| Postgres CDC (change data capture) / logical replication                   | `pg_replication` (verified, free) | https://dlthub.com/docs/dlt-ecosystem/verified-sources/pg_replication.md |
| MS SQL Server / Change Tracking, managed or hosted, need advanced features | `ms_sql` (hub, **paid**) | https://dlthub.com/docs/hub/ecosystem/ms-sql |
| _add more as discovered: check dlthub and verified sources_                | | |

> **Note:** All sources from the dlthub require the `dlthub` package and an active paid license. Always inform the user before recommending a dlthub source.

Tell the user which source fits and the install/init command. Do not continue with `sql_database` for these cases — the wrong source will produce incorrect or incomplete results.

**Also search the dlt hub** for the specific database type — community and ecosystem sources are not listed by `dlt init --list-sources`:
```
https://dlthub.com/docs/hub
```

**Then run** to check verified sources for any SaaS product built on top of the database (e.g. `salesforce`, `hubspot`):
```
dlt --non-interactive init --list-sources
```

If a maintained connector exists, inform the user — it is almost always better than building from scratch.

### 3. Set up credentials

Never ask the user to provide credentials directly. All credentials must go through `secrets.toml` and `config.toml`.

Use the **`setup-secrets`** skill to configure credentials. It will write the correct fragment to `.dlt/secrets.toml` safely without exposing values.

### 4. Explore available tables

Once credentials are configured, connect and list tables using a quick Python snippet:

```python
from sqlalchemy import create_engine, inspect

engine = create_engine("<connection_url>")
inspector = inspect(engine)
schemas = inspector.get_schema_names()
for schema in schemas:
    tables = inspector.get_table_names(schema=schema)
    print(f"Schema: {schema} — Tables: {tables}")
```

Run this so the user can see what's available. If the database is not yet reachable, skip and note this for the next skill.

### 5. Pick tables, destination, and backend

Ask the user — **do not proceed until all five questions are answered**:

1. **Which table(s)** to load first (start with one for the initial pipeline)
2. **Destination** if not provided (default: `duckdb`)
3. **Do you need dlt normalization?** dlt normalizes schema, coerces types, and standardizes column names. Skip it if you want data loaded as-is. **Wait for an explicit yes/no before continuing.**
4. **Do you need to transform data before or during loading?** (e.g. filter rows, pseudonymize values, apply business logic) **Wait for an explicit yes/no before continuing.**
5. **What reflection level do you need?** Controls how much schema metadata is read from the database:
   - `minimal` — column names and nullability only; types inferred from the data
   - `full` — column names, nullability, and data types including decimal precision/scale (**default**, recommended for most cases)
   - `full_with_precision` — maximum detail including precision for text and binary columns; may cause type-mismatch errors on some destinations
   Ref: https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/advanced#column-reflection

**Backend based on normalization need and data size** (cross-reference with data volume from step 1 of `create-sql-database-pipeline`):

- Normalization needed → `backend="sqlalchemy"` (any size)
- No normalization, small data (< 100k rows) → `backend="sqlalchemy"` (simpler, no extra deps)
- No normalization, medium/large data → `backend="pyarrow"` or `backend="connectorx"`

Suggest starting with a single small or representative table to validate the pipeline end-to-end before adding more.

### 6. Summarize and hand off

Present a one-line summary:
```
Source:            <dialect> database at <host>/<dbname>
Table:             <table_name> (schema: <schema or default>)
Destination:       <destination>
Backend:           <backend>
Driver:            <package>
Reflection level:  <minimal | full | full_with_precision>
Transform before load: <brief description, e.g. "filter rows by status=active", "pseudonymize email column", "cast decimal columns" — or "none">
```

Then proceed to `create-sql-database-pipeline` with this information. If transformations are needed, address them in step 7 (Add transformation callbacks).
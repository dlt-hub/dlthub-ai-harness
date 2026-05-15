---
name: create-sql-database-pipeline
description: Create a dlt pipeline from a SQL database source (postgres, mysql, mssql, oracle, sqlite, or any SQLAlchemy-supported database). Use when the user wants to load tables from a relational database to a destination like DuckDB, BigQuery, or Snowflake. Not for REST APIs or file sources.
argument-hint: "[database-url-or-description] [destination]"
---

# Create a SQL database dlt pipeline

Build the simplest working pipeline — one table, no incremental loading — to get data flowing fast.

**Docs:** https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/basic

Parse `$ARGUMENTS`:
- `database` (required): description of the source database (e.g. "postgres on localhost", "Rfam MySQL", a connection URL, or just the DB type)
- `destination` (optional, default `duckdb`): where to load data

## Steps

### 1. Assess data volume

Ask the user: **how much data will be loaded?** (approximate row count or table size is enough)

Note the answer — it will be used in step 10 to recommend the right backend and `chunk_size`.

Key rules regardless of scale:
- **Always pass `table_names=`** to `sql_database()` — avoids reflecting the entire schema
- **Large tables need incremental loading** — full reload of tens of millions of rows on every run is almost never the right plan; flag this to the user before writing code

### 2. Snapshot current folder

Run `ls -la` to see the current state before scaffolding.

### 3. Run dlt init

```
dlt init sql_database <destination> --non-interactive
```

This creates:
- `sql_database_pipeline.py` — working example
- `.dlt/secrets.toml` — credentials template
- `.dlt/config.toml` — pipeline config
- `requirements.txt`, `.gitignore`

Run `ls -la` again to confirm what was created.

### 4. Research before writing code

Do these in parallel:

**Read essential dlt docs upfront:**
- SQL database source overview: `https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/basic.md`
- Backend options and performance: `https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/configuration.md`
- Credentials setup: `https://dlthub.com/docs/general-usage/credentials/setup.md`

**Identify the driver:**

Different databases need different SQLAlchemy dialect + driver packages:

| Database | drivername | extra package |
|---|---|---|
| PostgreSQL | `postgresql+psycopg2` | `psycopg2-binary` |
| MySQL / MariaDB | `mysql+pymysql` | `pymysql` |
| MS SQL Server | `mssql+pyodbc` | `pyodbc` |
| Oracle | `oracle+cx_oracle` | `cx_Oracle` |
| SQLite | `sqlite` | _(built-in)_ |

Install the driver + sql_database extras if missing:
```
uv add "dlt[sql_database]" <driver-package>
```

### 5. Read generated files

Read the following (do NOT read `secrets.toml`):
- `sql_database_pipeline.py` — read for scaffold patterns, then replace its contents with the real pipeline in step 6
- `.dlt/config.toml` — pipeline config structure

### 6. Write the pipeline

**Replace the scaffold** — write the real pipeline into the generated `sql_database_pipeline.py`, or rename the file to match the use case (e.g. `movies_pipeline.py`). Either way: do not create a second file alongside the scaffold. The scaffold has no further purpose once replaced.

**Choose one scenario based on how many tables to load:**

#### Scenario A — Single table: use `sql_table`

```python
import dlt
from dlt.sources.sql_database import sql_table


def main() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="<name>",
        destination="<destination>",
        dataset_name="<name>",
        dev_mode=True,       # fresh timestamped dataset on each run
        progress="log",      # NOTE: progress goes on dlt.pipeline(), NOT on pipeline.run()
    )

    table = sql_table(
        table="<table_name>",
        chunk_size=500,
        # schema="<schema>",  # set if not the default schema
    )

    load_info = pipeline.run(table.add_limit(1), write_disposition="replace")
    print(load_info)


if __name__ == "__main__":
    main()
```

#### Scenario B — Multiple tables: use `sql_database`

```python
import dlt
from dlt.sources.sql_database import sql_database


def main() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="<name>",
        destination="<destination>",
        dataset_name="<name>",
        dev_mode=True,
        progress="log",
    )

    source = sql_database(
        schema="<schema>",           # set if not the default schema
        table_names=["<t1>", "<t2>"],  # always pass table_names — avoids full-schema reflection
        chunk_size=500,
    )

    load_info = pipeline.run(source.add_limit(1), write_disposition="replace")
    print(load_info)


if __name__ == "__main__":
    main()
```

Key rules:
- `progress="log"` belongs on `dlt.pipeline()`, **not** on `pipeline.run()` — that parameter does not exist on `run()`
- `dev_mode=True` creates a new timestamped dataset on every run — keeps test runs non-destructive
- `.add_limit(1)` loads one chunk only — always use for first/test runs
- **Always pass `table_names=`** to `sql_database()` — omitting it reflects the entire schema, which is slow and loads unwanted tables
- Do not hardcode credentials in the script — they are auto-injected from `.dlt/secrets.toml`

### 7. Apply reflection level

Using the reflection level chosen in `find-source`, set it on the source:

```python
# Scenario A
table = sql_table(table="<table_name>", chunk_size=500, reflection_level="full")

# Scenario B
source = sql_database(table_names=[...], chunk_size=500, reflection_level="full")
```

- `minimal` — column names and nullability only; types inferred from data. Use when `full` causes casting errors.
- `full` — column names, nullability, and data types including decimal precision/scale. Default; works for most cases.
- `full_with_precision` — maximum detail including precision for text/binary. Use when the destination requires strict typing; may cause type-mismatch errors.

Ref: https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/advanced#column-reflection

### 8. Add transformation callbacks (if needed)

If the user needs to transform data before or during loading, introduce the right tool depending on when the transformation happens:

- **Filter rows at SQL level** — `query_adapter_callback`:
  ```python
  def query_adapter(query, table):
      if table.name == "orders":
          return query.where(table.c.status == "active")
      return query

  source = sql_database(query_adapter_callback=query_adapter)
  ```

- **Add or modify columns at schema level** — `table_adapter_callback` to append computed columns before extraction.

- **Transform rows after extraction** — `add_map` on a resource:
  ```python
  def pseudonymize(row):
      row["email"] = hash(row["email"])
      return row

  source.orders.add_map(pseudonymize)
  ```

Ref: https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/usage

If no transformation is needed, skip this step.

> **Boundary:** these callbacks are for *extraction-time* transforms — filtering, masking, or reshaping data before it hits the destination. For *post-load* modeling (Kimball dimensions, CDM, cross-source joins) hand off to the **transformations** toolkit instead.

### 9. Set up config and secrets

**Config** (non-secret values like schema name, table name):

Edit `.dlt/config.toml` directly:

```toml
# .dlt/config.toml
[sources.sql_database]
table_name = "<table>"
```

**Secrets** (credentials): **never** read or write `secrets.toml` directly.

Present this template to the user and ask them to fill it in. Use `secrets_update_fragment` MCP tool (or `dlt ai secrets` CLI) to write the fragment — do not edit the file directly:

```toml
# .dlt/secrets.toml
[sources.sql_database.credentials]
drivername = "<dialect+driver>"        # e.g. mysql+pymysql, postgresql+psycopg2
host = "<host>"
port = <port>
username = "<username>"
password = "<password>"
database = "<database>"
```

A connection string is also accepted:
```toml
[sources.sql_database.credentials]
credentials = "<dialect+driver>://user:password@host:port/database"
```

**ALWAYS Get Feedback** before running for the first time. Show a summary of the files you changed or created, and confirm the user has filled in credentials.

### 10. Debug pipeline — first run

When user is ready, run:
```
uv run python <pipeline_script>.py
```

Expected output shows extract/normalize/load steps with row counts and timing from `progress="log"`.

**When errors occur, use `debug-pipeline`** to diagnose — do not add more complexity first.

Common first-run errors:
- `ConfigFieldMissingException` — a credentials field is missing or misnamed in secrets.toml
- `OperationalError` / `Can't connect` — wrong host/port/credentials or DB unreachable
- `ModuleNotFoundError: No module named 'sqlalchemy'` — run `uv add "dlt[sql_database]"`
- `MissingDependencyException: numpy required` — the pyarrow backend also needs numpy: `uv add numpy`

### 11. Suggest backend after a successful test run

Using the data volume noted in step 1, recommend the right backend:

| Scale | Rows / Size | Recommended backend | chunk_size |
| --- | --- | --- | --- |
| Small | < 100k rows / < 500 MB | `sqlalchemy` (default) | any |
| Medium | 100k – 10M rows / 500 MB – 10 GB | `pyarrow` (needs `numpy`) | 5000 |
| Large | > 10M rows / > 10 GB | `connectorx` (MySQL/Postgres) or `pyarrow` | 50000 |

Backend options:
- **`sqlalchemy`** — safest, works with every destination, but slowest.
- **`pyarrow`** — 20–30x faster; preserves decimal/date types precisely. Also requires `numpy`.
- **`pandas`** — convenient for DataFrame workflows, but loses precision on decimal and date columns.
- **`connectorx`** — fastest overall (2x over pyarrow, Rust-based); uses its own connection string format, bypasses SQLAlchemy.

Ref: https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/configuration#configuring-the-backend

Apply the chosen backend:
```python
table = sql_table(table="<table_name>", chunk_size=500, backend="pyarrow")
```

Re-run the test to confirm the backend works before moving on.

> **Note:** When using `pyarrow`, `pandas`, or `connectorx` (normalization skipped), `apply_hints` works for incremental loading, write disposition, merge keys, etc. — but schema changes like `columns={...}` do not work. Use `table_adapter_callback` for column-level schema changes instead.

## Next steps

- **Test run succeeded, backend chosen** → use `adjust-table` to remove limits and add incremental loading for production
- **Pipeline errors or 0 rows** → use `debug-pipeline` to inspect traces and load packages
- **Want more tables** → use `add-table` to add resources to the pipeline
- **Ready to explore data** → hand over to **data-exploration** toolkit
- **Ready to deploy** → hand over to **dlthub-platform** toolkit

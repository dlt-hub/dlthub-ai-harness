---
name: add-table
description: Add a new table or view to an existing dlt SQL database pipeline. Use when the user wants to load additional tables from the same database that already has a working pipeline.
argument-hint: "[table-name]"
---

# Add a table to an existing pipeline

Extend an existing SQL database pipeline with a new table or view from the same source.

Parse `$ARGUMENTS`:
- `table-name` (required): the table or view to add (e.g. "orders", "public.users", "vw_daily_summary")

## Steps

### 1. Read the existing pipeline

Read the pipeline `.py` file to understand:
- Whether it uses `sql_table` (single resource) or `sql_database` (multiple resources)
- The current backend (`sqlalchemy`, `pyarrow`, etc.)
- Write disposition (`replace`, `merge`, `append`)
- Incremental loading setup (if any)
- How `__main__` runs the pipeline (`dev_mode`, `add_limit`, `with_resources`)

### 2. Research the new table

Connect to the DB or check the source DB docs to understand:
- Exact table/view name and schema
- Column names, types, and nullability
- Whether it has a good incremental cursor column (e.g. `updated_at`, `created_at`, `id`)
- Row count — large tables may need a different backend or incremental loading from the start

### 3. Add the table

#### A. Pipeline uses `sql_table` — switch to `sql_database`

If the pipeline loads a single table with `sql_table`, switch to `sql_database` to handle multiple:

```python
from dlt.sources.sql_database import sql_database

source = sql_database(
    table_names=["existing_table", "new_table"],
    backend="pyarrow",  # match the existing backend
)
pipeline.run(source.add_limit(1), write_disposition="replace")
```

#### B. Pipeline already uses `sql_database` — add to `table_names`

```python
source = sql_database(
    table_names=["existing_table", "new_table"],  # add here
)
```

### 4. Test the new table in isolation

Use `with_resources()` to load only the new table without re-loading existing ones:

```python
source = sql_database(table_names=["existing_table", "new_table"])
pipeline.run(source.with_resources("new_table").add_limit(1))
```

Run the pipeline:
```
uv run python <name>_pipeline.py
```

Use `debug-pipeline` after each run to inspect traces and load packages.

### 5. Review consistency with existing tables

Check if the new table should adopt the same patterns as existing ones:

- **Backend** — use the same backend for consistency unless the new table has special needs
- **Incremental loading** — if existing tables use `incremental`, should the new one too?
- **Write disposition** — match `replace`/`merge`/`append` unless there's a reason not to

Flag any gaps to the user.

### 6. Report

```
Table added: <table_name>
- Destination table: <normalized_name>
- Backend: <backend>

Load with:
  source.with_resources("<table_name>")   # just this table
  source                                  # all tables

Available tables: <list all table names>
```

## Next steps

- **All tables loaded correctly** → use `validate-data` to check schemas and data
- **Errors on the new table** → use `debug-pipeline` to inspect traces
- **New table needs incremental loading** → use `adjust-table`

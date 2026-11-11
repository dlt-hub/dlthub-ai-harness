---
name: add-table
description: Add a new table or view to an existing dlt SQL database pipeline. Use when the user wants to load additional tables from the same database that already has a working pipeline.
argument-hint: "[table-name]"
---

# Add a table to an existing pipeline

## Prerequisites
Skip this if you already checked it in this session.
1. Run `uv --version`. If it fails, `uv` is missing.
   - Ask the user to allow the `uv` install. Do not install it without approval.
   - On macOS and Linux, run `curl -LsSf https://astral.sh/uv/install.sh | sh`.
   - On Windows, run `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.
   - Docs: https://docs.astral.sh/uv/getting-started/installation/
   - If `uv` is still not found, tell the user to open a new shell, because the install changes `PATH`.
2. Run `uv run dlthub ai status`. If it fails, `dlt[hub]` or the dlthub workspace is missing.
3. Check that these skills are available. If a skill is not available, its toolkit is missing.
   - `setup-secrets` from the `init` toolkit
   - Do not check the `dlt-workspace-mcp` tools. They do not start without `dlt[hub]`.
4. Find how this skill was installed. Look at the folder of this skill.
   - The folder is in the project (`.claude/`, `.cursor/` or `.agents/`): the `dlthub` CLI installed it.
   - The folder is not in the project: a plugin marketplace installed it.
5. If anything is missing, tell the user that this skill does not work without it.
   - Ask the user to allow each install.
   - Install from the same channel as this skill. Then each toolkit has only one copy.
6. The `dlthub` CLI installed this skill:
   - If `dlt[hub]` or `init` is missing, run `uvx dlthub-init@latest`. It installs both.
   - For each other missing toolkit, run `uv run dlthub --non-interactive ai toolkit install <toolkit>`.
7. A plugin marketplace installed this skill:
   - If `dlt[hub]` or the workspace is missing, run `uvx --from "dlt[hub]" dlthub init`.
   - Do not run `uvx dlthub-init@latest`. It adds a second copy of `init`.
   - Ask the user to install each missing toolkit from the same marketplace.
   - In Claude Code, the command is `/plugin install <toolkit>@dlthub-ai-harness`.
8. After the install, tell the user to restart the session. Skills, rules and MCP load only at session start.
9. If the user refuses an install, stop. Do not run other steps of this skill.

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

Use `debug-sql-database-pipeline` after each run to inspect traces and load packages.

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

- **All tables loaded correctly** → use `validate-sql-database-data` to check schemas and data
- **Errors on the new table** → use `debug-sql-database-pipeline` to inspect traces
- **New table needs incremental loading** → use `adjust-table`

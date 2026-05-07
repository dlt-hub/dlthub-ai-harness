---
name: validate-data
description: Validate schema and data after a successful dlt SQL database pipeline load. Use when the user wants to check if loaded data looks correct, inspect table schemas, fix data types, or verify column mappings from the source database.
argument-hint: "[pipeline-name] [concerns]"
---

# Validate loaded data

After a successful pipeline load, verify the schema and data make sense.

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline name. If omitted, infer from session context. If ambiguous, ask the user and stop.
- `hints` (optional, after `--`): specific validation concerns (e.g. "decimal precision", "missing columns")

## 1. Inspect schema

### Export schema as mermaid

```
dlt pipeline <pipeline_name> schema --format mermaid
```

Show the mermaid diagram to the user. This gives a quick overview of tables, columns, types, and relationships.

## 2. View the data

### For the human: Workspace Dashboard

Tell the user to run the Workspace Dashboard:
```
dlt pipeline <pipeline_name> show
```
This opens a browser with table schemas, row counts, and sample data.

### For the agent: query via pipeline dataset API

```python
import dlt

pipeline = dlt.attach("<pipeline_name>")
dataset = pipeline.dataset()

# Row counts for all tables
dataset.row_counts().df()

# Sample rows from a table
dataset["<table_name>"].head().df()
```

Never import the destination library (e.g. `duckdb`) directly — use `pipeline.dataset()` instead, which is destination-agnostic.

## 3. Review with user

Ask the user if the schema and data look right. Common issues for SQL sources:

### Data type mismatches

The default `sqlalchemy` backend reflects types from the source DB. If types look wrong after switching backends (e.g. to `pyarrow`), check `reflection_level`:

```python
sql_table(
    table="<table>",
    reflection_level="full_with_precision",  # preserves decimal scale and string length
)
```

**IMPORTANT:** Never convert monetary or precision-sensitive values to `float`. Always keep them as `Decimal`.

### Missing or null columns

Columns that are all-null on first load won't have inferred types. Add explicit column hints:

```python
sql_table(
    table="<table>",
    columns={"amount": {"data_type": "decimal", "precision": 18, "scale": 4}},
)
```

> **Note:** `columns={}` hints do not work with backends that skip dlt normalisation (`pyarrow`, `pandas`, `connectorx`). If you need schema hints and are using one of those backends, use `table_adapter_callback` instead.

### Unexpected column names

dlt normalizes column names to snake_case by default. If source DB column names contain spaces or special chars, they are renamed. Check the schema mermaid output to see the mapped names.

## 4. Iterate

Re-run the pipeline after changes (`dev_mode=True` gives a fresh dataset each time). Use `debug-pipeline` to inspect traces after each run. Repeat until the user is satisfied with the schema.

## Next steps

- **User is happy with the data** → use `adjust-table` to remove limits and configure incremental loading for production
- **Need to add more tables** → use `add-table`
- **Need to fix pipeline code** → edit and re-run with `debug-pipeline`
- **User wants to explore data** → hand over to **data-exploration** toolkit for notebooks and charts

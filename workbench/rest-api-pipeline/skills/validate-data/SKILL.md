---
name: validate-data
description: Validate schema and data after a successful dlt pipeline load. Use when the user wants to check if loaded data looks correct, inspect table schemas, fix data types, flatten nested structures, or refine the data shape.
argument-hint: "[pipeline-name] [concerns]"
---

# Validate loaded data

After a successful pipeline load, verify the schema and data make sense. Fix data types, nested structures, and missing columns as needed.

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline name. If omitted, infer from session context. If ambiguous, ask the user and stop.
- `hints` (optional, after `--`): specific validation concerns

## 1. Inspect schema

### Export schema as mermaid

```
dlt pipeline <pipeline_name> schema --format mermaid
```
Show the mermaid diagram to the user. This gives a quick overview of tables, columns, types, and relationships (parent/child).

## 2. View the data

### For the human: Workspace Dashboard

Tell the user to run Workspace Dashboard:
```
dlt pipeline <pipeline_name> show
```
This opens a browser with table schemas, row counts, and sample data.

### For the agent: set up pipeline MCP server to query the data

You have mcp with a right set of tools available

## 3. Review with user

Ask the user if the schema and data look right. Common issues to address:

### Data type fixes

Use `processing_steps` in the resource config to transform data before loading. Available steps: `map`, `filter`, `yield_map`.

```python
"processing_steps": [
    {"map": lambda item: {**item, "amount": Decimal(item["amount"])}},
]
```

**IMPORTANT:** NEVER convert monetary amounts or precision-sensitive values to `float`. Always use `Decimal`.

### Nested structures

dlt auto-unnests nested arrays into child tables (e.g., `results` inside a response becomes `<resource>__results`). This is often fine for analytics. If the user wants a flat structure, use `yield_map` to flatten, or adjust `data_selector` to point deeper into the response.

### Missing columns

Columns that are all-null on first load won't have inferred types. Options:
- Add `columns` hints to the resource config: `"columns": {"field": {"data_type": "text"}}`
- Add `group_by` or other API params to populate the columns

## 4. Iterate

Re-run the pipeline after changes (`dev_mode` gives a fresh dataset each time). Use `debug-pipeline` to inspect traces and load packages after each run. Inspect again with MCP or `dlt pipeline <name> schema --format mermaid`. Repeat until the user is happy with the schema.

## Next steps

- **User is happy with data** → suggest `new-endpoint` for more resources, `view-data` for querying, or the `data-exploration` toolkit for interactive notebooks and reports
- **Need to fix pipeline code** → edit and re-run with `debug-pipeline`
- **User wants to see the data** -> Workspace Dashboard with command above

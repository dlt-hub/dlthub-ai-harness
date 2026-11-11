---
name: validate-data
description: Validate schema and data after a successful dlt pipeline load. Use when the user wants to check if loaded data looks correct, inspect table schemas, fix data types, flatten nested structures, or refine the data shape.
argument-hint: "[pipeline-name] [concerns]"
---

# Validate loaded data

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

After a successful pipeline load, verify the schema and data make sense. Fix data types, nested structures, and missing columns as needed.

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline name. If omitted, infer from session context. If ambiguous, ask the user and stop.
- `hints` (optional, after `--`): specific validation concerns

## 1. Inspect schema

### Export schema as mermaid

```
uv run dlthub local pipeline schema <pipeline_name> --format mermaid
```
Show the mermaid diagram to the user. This gives a quick overview of tables, columns, types, and relationships (parent/child).

## 2. View the data

### For the human: Workspace Dashboard

Tell the user to run Workspace Dashboard:
```
uv run dlthub local pipeline show <pipeline_name>
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

Re-run the pipeline after changes (`dev_mode` gives a fresh dataset each time). Use `debug-pipeline` to inspect traces and load packages after each run. Inspect again with MCP or `dlthub local pipeline schema <name> --format mermaid`. Repeat until the user is happy with the schema.

## Next steps

- **User is happy with data** → suggest `new-endpoint` for more resources, `view-data` for querying, or the `data-exploration` toolkit for interactive notebooks and reports
- **Need to fix pipeline code** → edit and re-run with `debug-pipeline`
- **User wants to see the data** -> Workspace Dashboard with command above

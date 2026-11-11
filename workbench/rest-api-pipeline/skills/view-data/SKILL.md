---
name: view-data
description: Query, explore, or view data loaded by a dlt pipeline. Use when the user asks to query data, explore loaded tables, check row counts, write Python that reads pipeline data, or asks questions like "show me the data", "what users are there", "how much did we spend". Covers dlt dataset API, ibis expressions, and ReadableRelation.
argument-hint: "[pipeline-name] [query]"
---

# View pipeline data

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

Query data loaded by a dlt pipeline using Python. Use in standalone scripts, inline code, or as the data access layer for reports.

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline name. If omitted, infer from session context. If ambiguous, ask the user and stop.
- `hints` (optional, after `--`): additional requirements or focus areas (e.g., `-- show top users by spend`)

## Workspace Dashboard UI if just exploring

Tell the user to run Workspace Dashboard **if no precise query or instructions were give**, this
assumes user wants to just look at the data. Otherwise
```
uv run dlthub local pipeline show <pipeline_name>
```
This opens a browser with table schemas, row counts, and sample data.

## dlt dataset API for ad hoc reports

**Essential Reading:**
- `https://dlthub.com/docs/general-usage/dataset-access/dataset.md`
- `https://dlthub.com/docs/general-usage/dataset-access/dataset#modifying-queries-with-ibis-expressions`

Use `pipeline.dataset()` to access loaded data. This is **destination agnostic** — works the same on duckdb, postgres, bigquery, etc. NEVER import destination libraries (like `duckdb`) directly.

### Attach to pipeline and get dataset
```python
import dlt
pipeline = dlt.attach("<pipeline_name>")
dataset = pipeline.dataset()
```

### ReadableRelation (dlt native)
Think about it as a subset of ibis with slightly different syntax.
```python
table = dataset["my_table"]
table.head().df()                              # first rows as pandas
table.select("id", "name").limit(50).arrow()   # select columns, arrow format
table.where("id", "in", [1, 2, 3]).df()        # parametric filter
table.select("amount").max().fetchscalar()      # scalar aggregate
dataset.row_counts().df()                       # row counts for all tables
```

### Ibis expressions (preferred for complex queries)
```python
t = dataset["my_table"].to_ibis()
expr = t.filter(t.amount > 100).group_by("category").aggregate(total=t.amount.sum())
dataset(expr).df()  # execute ibis expression via dataset
```

Ibis is lazy, composable, and destination agnostic. Key operations:
- `table.group_by("col").aggregate(total=table.col.sum())` — aggregation
- `table.filter(table.col > 0)` — filtering
- `table.join(other, table.id == other.parent_id)` — joins
- `table.order_by(ibis.desc("col"))` — sorting
- `table.mutate(new_col=table.col * 100)` — computed columns
- `table.select("col1", "col2")` — column selection

Read ibis docs: `https://ibis-project.org/reference/expression-tables`

### Joining parent/child tables

dlt creates child tables for nested data (e.g., `my_table__results`). Join on `_dlt_id` / `_dlt_parent_id`:
```python
parent = dataset["my_table"].to_ibis()
child = dataset["my_table__results"].to_ibis()
joined = parent.join(child, parent._dlt_id == child._dlt_parent_id)
```

### Raw SQL (when needed)
```python
dataset("SELECT * FROM my_table WHERE amount > 100").df()
```

## Custom charts and insights

If the user wants to create custom charts or generate insights from their data, install the **data-exploration** toolkit (`dlthub ai toolkit install data-exploration`) and follow the workflow there.

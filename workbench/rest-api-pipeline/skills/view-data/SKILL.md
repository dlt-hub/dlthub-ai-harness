---
name: view-data
description: Query, explore, or view data loaded by a dlt pipeline. Use when the user asks to query data, explore loaded tables, check row counts, write Python that reads pipeline data, or asks questions like "show me the data", "what users are there", "how much did we spend". Covers dlt dataset API, ibis expressions, and ReadableRelation.
argument-hint: "[pipeline-name] [query]"
---

# View pipeline data

Query data loaded by a dlt pipeline using Python. Use in standalone scripts, inline code, or as the data access layer for reports.

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline name. If omitted, infer from session context. If ambiguous, ask the user and stop.
- `hints` (optional, after `--`): additional requirements or focus areas (e.g., `-- show top users by spend`)

## Workspace Dashboard UI if just exploring

Tell the user to run Workspace Dashboard **if no precise query or instructions were give**, this
assumes user wants to just look at the data. Otherwise
```
dlt pipeline <pipeline_name> show
```
This opens a browser with table schemas, row counts, and sample data.

## dlt dataset API for ad hoc reports

**Essential Reading:**
- `https://dlthub.com/docs/general-usage/dataset-access/dataset.md`
- `https://dlthub.com/docs/general-usage/dataset-access/ibis-backend.md`

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

Read ibis docs: `https://ibis-project.org/reference/expression-collections`

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

If the user wants to create custom charts or generate insights from their data, install the **data-exploration** toolkit (`dlt ai toolkit data-exploration install`) and follow the workflow there.

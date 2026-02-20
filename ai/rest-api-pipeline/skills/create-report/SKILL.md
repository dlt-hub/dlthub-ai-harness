---
name: create-report
description: Create an interactive marimo notebook to visualize and report on pipeline data. Use when the user wants a dashboard, charts, visual analysis, or a marimo notebook for data exploration. For data access patterns, see view-data skill.
argument-hint: <pipeline-name>
---

# Create a data report

Create an interactive marimo notebook to visualize and explore data loaded by a dlt pipeline. Uses the dlt dataset API from `view-data` skill for data access.

Parse `$ARGUMENTS`:
- `pipeline-name` (required): the dlt pipeline name (e.g., `anthropic_usage_pipeline`)

## 1. Understand the data

Before writing code, understand what data is available and what the user wants from it.

### Inspect the schema
```
dlt pipeline <pipeline_name> schema --format mermaid
```
Show the mermaid diagram to the user — tables, columns, types, relationships.

### Query sample data

Use MCP tools or the `view-data` dataset API to get:
- Row counts per table
- Sample rows from key tables
- Value distributions for important columns (distinct values, min/max, nulls)

### Research the data domain

Do a short web search to understand the data source context:
- What do the fields mean?
- What are typical analysis patterns for this kind of data?
- What metrics matter to users of this data?

### Present a data summary to the user

Describe the data in **business terms**, not technical terms. Example:
```
Your data covers Feb 10–17, 2026 and contains:
- Daily API usage by model (3 models, ~335M tokens on opus alone)
- Daily costs ($491 total over 7 days)
- Cache efficiency metrics (cache reads vs uncached input)

Available dimensions: model, api_key_id, workspace_id, service_tier
```

### Ask the user what they want to explore

Suggest 3-4 concrete analysis directions based on the data. Ask: **What's the goal — monitoring, optimization, reporting, or something else?**

## 2. Create a marimo notebook

Create `<pipeline_name>_explore.py` as a marimo notebook. marimo notebooks are pure Python files with `@app.cell` decorators.

Install if needed: `pip install "dlt[workspace]"` (includes marimo + ibis).

**Before launching, verify the notebook runs without errors:**
```
uv run python <pipeline_name>_explore.py
```
Fix any errors before proceeding. Only launch once it runs cleanly.

Launch with watch mode so edits auto-reload:
```
marimo edit --watch --no-token <pipeline_name>_explore.py
```

## 3. Connect to pipeline data

Use `dlt.attach()` and `dataset()` — see `view-data` skill for the full API reference.

```python
@app.cell
def _():
    import dlt
    pipeline = dlt.attach("<pipeline_name>")
    dataset = pipeline.dataset()
    return dataset, pipeline
```

Get ibis table expressions from the dataset:
```python
@app.cell
def _(dataset):
    my_table = dataset["table_name"].to_ibis()
    return (my_table,)
```

## 4. Build analysis cells with ibis

Use **ibis expressions** for all data queries — NOT raw SQL, NOT pandas operations. Return bare ibis expressions from cells — marimo renders them in its built-in interactive data explorer:

```python
@app.cell
def _(my_table, ibis):
    user_summary = (
        my_table
        .group_by("user")
        .aggregate(total=my_table.amount.sum())
        .order_by(ibis.desc("total"))
    )
    return (user_summary,)

@app.cell
def _(user_summary):
    user_summary  # bare return → marimo data explorer
    return
```

## 5. Add charts with altair

Use `mo.ui.altair_chart()` for interactive charts with click-to-filter.

**IMPORTANT — marimo naming rule:** Variable names must be unique across all cells. If you reuse a name like `chart` in multiple cells, marimo will raise a `MultipleDefinitionError` and break those cells. Use `_`-prefixed names (e.g. `_chart`) for cell-local variables — they are private and exempt from the uniqueness rule. The preferred pattern is to inline the chart as the last expression so no variable is needed at all:

```python
# Preferred: inline as last expression — no naming conflict possible
@app.cell
def _(mo, alt, my_data):
    mo.ui.altair_chart(
        alt.Chart(my_data.to_pandas()).mark_bar().encode(x="category", y="total")
    )
    return

# Also fine: use _ prefix to make the variable cell-local
@app.cell
def _(mo, alt, my_data):
    _chart = mo.ui.altair_chart(
        alt.Chart(my_data.to_pandas()).mark_bar().encode(x="category", y="total")
    )
    _chart
    return

# WRONG: reusing `chart` across cells causes MultipleDefinitionError
@app.cell
def _(mo, alt, my_data):
    chart = mo.ui.altair_chart(...)  # breaks if another cell also defines `chart`
    chart
    return (chart,)
```

## 6. Add markdown headers

Use `mo.md()` for section titles and context. Keep text short — the data explorer does the heavy lifting.

```python
@app.cell
def _(mo):
    mo.md("## Cost by User and Model")
    return
```

## 7. Iterate with the user

The notebook is a conversation tool. After the initial version:
- Ask if the views are useful
- Add/modify cells based on feedback
- Suggest additional analyses based on what the data reveals
- If data is missing, suggest pipeline changes (new endpoints, different params)

# Marimo Notebook Patterns

Complete cell templates for generating `<pipeline_name>_dashboard.py`.

The templates below are dlt-dashboard-specific. For general marimo patterns, see the `marimo-notebook` skill (checked in SKILL.md).

## PEP 723 header

```python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo",
#     "dlt[duckdb]",
#     "ibis-framework[duckdb]",
#     "altair",
#     "vl-convert-python",
# ]
# ///
```

Add dependencies only if the spec's ibis code uses additional libraries.

## App setup cell

```python
import marimo

app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import altair as alt
    import ibis
    import dlt
    return alt, dlt, ibis, mo
```

## Connection cell

```python
@app.cell
def _(dlt):
    pipeline = dlt.attach("<pipeline_name>")
    dataset = pipeline.dataset()
    return dataset, pipeline
```

## Per-chart cells (two cells per Chart N in spec)

### Data cell — executes the ibis query from the spec

```python
@app.cell
def _(dataset):
    t = dataset["orders"].to_ibis()
    monthly = (
        t.mutate(month=t.created_at.truncate("M"))
        .group_by("month")
        .aggregate(revenue=t.amount.sum())
        .order_by("month")
        .limit(1000)
    )
    df_chart1 = dataset(monthly).df()
    return (df_chart1,)
```

### Chart cell — renders with `mo.ui.altair_chart()` for interactivity

```python
@app.cell
def _(alt, df_chart1, mo):
    _chart = alt.Chart(df_chart1).mark_line().encode(
        x="month:T",
        y="revenue:Q",
        tooltip=["month:T", "revenue:Q"]
    ).properties(title="Monthly Revenue Trend")
    _chart
    return
```
### Critical: every chart cell MUST end with `return`

Marimo displays whatever a cell returns. If a chart cell has no `return` statement, nothing renders — even if `_chart` is on a bare line. Marimo's auto-formatter may also strip bare expressions.


**Never use:**
```python
_chart  # bare expression — will be stripped by formatter
mo.ui.altair_chart(_chart)  # no return — nothing renders
```

## App entry point

```python
if __name__ == "__main__":
    app.run()
```

No footer cell — marimo's linter flags trivial `mo.md()` cells as empty. The last chart cell is the visual end of the notebook.

## Cell naming conventions

- `df_chart1`, `df_chart2`, ... — dataframe variables, one per chart, avoids cross-cell conflicts
- `_chart` — underscore prefix keeps the altair object cell-local (not exported)
- Data cells return `(df_chartN,)` — tuple syntax exports the variable to dependent cells
- Chart cells **must** `return mo.ui.altair_chart(_chart)` — marimo displays whatever a cell returns. Without `return`, nothing renders. Do not use bare expressions or `print()`

# Marimo Notebook Patterns

Complete cell templates for generating `<pipeline_name>_dashboard.py`.

The templates below are dlt-dashboard-specific. For general marimo patterns, see the `marimo-notebook` skill (checked in SKILL.md).

## App setup cell

```python
import marimo

app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import altair as alt
    import dlt
    return alt, dlt, mo
```

> If any chart uses ibis expressions, add `import ibis` in the specific data cell that needs it — not in the global setup cell.

## Connection cell

```python
@app.cell
def _(dlt):
    pipeline = dlt.attach("<pipeline_name>")
    dataset = pipeline.dataset()
    return dataset, pipeline
```

## Per-chart cells (two cells per Chart N in spec)

### Data cell — executes the SQL query from the spec

```python
@app.cell
def _(dataset):
    df_chart1 = dataset("""
        SELECT
            DATE_TRUNC('month', created_at) AS month,
            SUM(amount) AS revenue
        FROM orders
        GROUP BY 1
        ORDER BY 1
    """).df()
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
### Critical: every chart cell MUST end with `_chart` then `return`

Chart cells **must** end with `_chart` on a bare line followed by `return` — this is what marimo displays. Without the bare `_chart` line, nothing renders.

**Wrong** (missing `_chart` before `return`):
```python
    ).properties(title="Monthly Revenue Trend")
    return
```

**Right** (`_chart` on its own line, then `return`):
```python
    ).properties(title="Monthly Revenue Trend")
    _chart
    return
```

## Markdown header cells

Use `mo.md()` for section titles and context. Keep text short — the data explorer does the heavy lifting.

```python
@app.cell
def _(mo):
    mo.md("## Cost by User and Model")
    return
```

Place header cells before chart groups to organize the dashboard into logical sections.

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
- Chart cells **must** end with `_chart` on a bare line followed by `return` — without the bare `_chart` line, nothing renders. Do not use `print()` or skip the `_chart` line

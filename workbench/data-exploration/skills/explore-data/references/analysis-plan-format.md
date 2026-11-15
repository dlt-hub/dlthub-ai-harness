# Analysis Plan Format Reference

The analysis plan is the structured artifact that `explore-data` writes and `build-notebook` reads. It lives in
the workspace at `.dlthub/explorations/<pipeline_name>/analysis_plan.md`, one plan per pipeline, and is
committed. Section headers are parsed mechanically — keep them exact.

The plan does not depend on the dashboard tool: each chart is a question, a SQL query and a chart spec.
`build-notebook` renders it as a marimo notebook; another renderer can read the same plan.

## Full template

```markdown
# Analysis Plan: <pipeline_name>

## Connection
pipeline: <pipeline_name, or empty for a standalone .duckdb file>
module: <module that creates the pipeline at the module level, for example pipelines.orders, or empty>
destination: <the destination of the pipeline: its name, for example warehouse, or its type, for example duckdb; the path of a standalone .duckdb file>
dataset: <dataset_name>

## Dashboard
path: <path of the dashboard file, for example orders_pipeline_dashboard.py>

## Profile Summary
| table | rows | key columns | notes |
|-------|------|-------------|-------|
| orders | 50k | id, amount, created_at, category | temporal: created_at |
| customers | 2k | id, name, email | PII: name, email |

## Questions
1. [x] How has revenue changed over time? → Chart 1
2. [ ] Which categories generate the most revenue?

## Data Gaps
(none — or: "customer_segment column needed, not in any table")

## Chart 1: Monthly Revenue Trend
added: 2026-03-10
question: How has revenue changed over time?
type: line
x: created_at (monthly)
y: sum(amount)
source: orders

```sql
SELECT
    DATE_TRUNC('month', created_at) AS month,
    SUM(amount) AS revenue
FROM orders
GROUP BY 1
ORDER BY 1
```

```altair
alt.Chart(df).mark_line().encode(
    x="month:T",
    y="revenue:Q",
    tooltip=["month:T", "revenue:Q"]
).properties(title="Monthly Revenue Trend")
```
```

## Notes

- **Profile Summary** may be minimal (table/column names only) on the high-intent path; full stats on low-intent path.
- **Dashboard** is empty until `build-notebook` writes the dashboard; it then records the path the user chose.
- Mark charted questions with `[x]`, remaining with `[ ]`.
- Append new `## Chart N` sections for each subsequent chart, with the date they were added — do not remove previous ones.
- `build-notebook` parses `## Chart N` sections to generate cells; keep the sql/altair code blocks labeled correctly.

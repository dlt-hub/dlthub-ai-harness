# Analysis Plan Format Reference

The analysis_plan.md file is the structured artifact that `explore-data` writes and `build-notebook` reads.
Section headers are parsed mechanically — keep them exact.

## Full template

```markdown
# Analysis Plan: <pipeline_name>

## Connection
pipeline: <pipeline_name>
dataset: <dataset_name>
destination: <destination_type>

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
- Mark charted questions with `[x]`, remaining with `[ ]`.
- Append new `## Chart N` sections for each subsequent chart — do not remove previous ones.
- `build-notebook` parses `## Chart N` sections to generate cells; keep the sql/altair code blocks labeled correctly.

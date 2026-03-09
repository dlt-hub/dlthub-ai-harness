---
name: analyze-questions
description: Generate one chart at a time from dlt pipeline data to answer a user's business question — interview, plan and confirm a single chart, then hand off to notebook generation. The workflow handles iteration. Use when the user wants to visualize their data, make charts, or explore what their pipeline shows. Runs after connect-and-profile. Do NOT use for connecting to pipelines or inspecting schemas (use connect-and-profile), or for generating the notebook itself (use marimo-notebook).
---

# Analyze questions and plan charts

Interview the user to surface their questions, then **plan and confirm a single chart** for their top-priority question. Hand off to notebook generation — the workflow rule handles iteration.

Lead with business questions, not schema details.

## Prerequisites

Requires profiling evidence from `connect-and-profile`: table names, row counts, key columns. If missing, run `connect-and-profile` first.

Plan charts for ibis queries and altair rendering — not pandas or raw SQL.

## Adding more charts

If an analysis plan already exists (default: `<pipeline_name>_analysis_plan.md`), skip the interview. Ask the user what new question they want to add, then jump to **Plan chart**.

## Interview

Use `AskUserQuestion` at every step — present concrete options inferred from the schema, never open-ended questions.

Summarize the profiling evidence in 2–3 bullets first (tables, row counts, key columns), then infer 3–5 plain-language business questions the data can answer. Present as multi-select:

```
question: "What questions do you want to answer? (Pick all that interest you — I'll create a chart for each)"
multiSelect: true
options:
  - label: "How has order revenue changed over time?"
    description: "orders table — monthly/weekly trends"
  - label: "Which customers spend the most?"
    description: "orders + users — rank by total spend"
  - label: "Other"
    description: "Describe your own question"
```

Avoid columns that may contain sensitive data — personally identifiable information (PII), payment card industry data (PCI), protected health information (PHI), and any other sensitive information — as chart dimensions or metrics.

## Plan chart

For the user's top-priority selected question, silently decide: which table(s), which metric and grouping columns, the appropriate time grain (if temporal), and the right chart type:

- Trend over time → **line chart**
- Comparison across categories → **bar chart**
- Relationship between two metrics → **scatter plot**
- Parts of a whole → **stacked bar or treemap**
- Distribution of a metric → **histogram or box plot**

If a question has both temporal and categorical aspects, pick the primary one first — the secondary becomes the next chart.

Before presenting, sanity-check the spec: does it actually answer the question? If not, rethink before showing it.

Then present the spec for confirmation:

```
question: "Here's the chart I've planned. Look good?"
options:
  - label: "Yes (Recommended)"
  - label: "Adjust"
    description: "Change the chart type, metric, or grouping"
```

Show the spec above the toggle:

```
Chart: Monthly Revenue Trend
Type: line chart
X: orders.created_at (monthly)
Y: sum(orders.amount)
Source: orders table (50k rows)
"Total order revenue over time, aggregated monthly"
```

If "Adjust", ask one targeted follow-up — don't re-run the full interview.

## Save analysis plan

After the spec is confirmed, append to `<pipeline_name>_analysis_plan.md`: the question and chart spec (type, axes, source table). Use exact column names from the schema.

## Handoff

Before invoking `marimo-notebook`, generate chart code for the confirmed spec:
- Write an ibis query that produces the data for the chart (use `dlt.attach()` to connect — see `rules/dlt-relation-api.md`)
- Write an altair chart from the query result. Sanity-check: does it aggregate at the right grain, is the metric summable, and does it directly answer the question?
- Wrap both in a marimo notebook file (`<pipeline_name>_dashboard.py`) using proper marimo cell structure

Then pass the notebook file path to the `marimo-notebook` skill. The workflow rule handles the dependency check, launch, and iteration loop — **do not plan or generate more than one chart per invocation**.

---
name: explore-data
argument-hint: "[pipeline-name] [question]"
description: This skill should be used when the user asks to "explore my data", "what can I learn from this pipeline", "what's the revenue trend", "show me charts", "visualize my pipeline", "what questions can I ask about my data", or wants to explore, profile, or chart data from a dlt pipeline. Connects to a pipeline, profiles tables or scans schema, plans charts with ibis + altair code, and writes an analysis_plan.md artifact. Do NOT use for building or fixing pipelines (use rest-api-pipeline toolkit), deploying pipelines (use dlthub-runtime toolkit), or assembling the marimo notebook from an analysis plan (use build-notebook).
---

# Explore data and plan charts

Connect to a dlt pipeline, understand the data, and plan one chart at a time. Outputs a `<date>_<pipeline_name>_analysis_plan.md` artifact that `build-notebook` consumes. Use today's date in `YYYY-MM-DD` format (e.g., `2026-03-10`).

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline name. If omitted, infer from session context. If ambiguous, ask the user and stop.
- `question` (optional, after `--`): a specific business question (e.g., `-- what's the revenue trend?`)

## Session context — skip redundant work

Before discovery, check what's already available:

1. **Pipeline already known** — if `pipeline-name` was passed via `$ARGUMENTS` or the session already has a pipeline context (e.g., arriving from `rest-api-pipeline` after `validate-data` or `view-data`), skip `list_pipelines` and go straight to `list_tables`.
2. **Existing analysis_plan.md** — if `*_analysis_plan.md` exists, skip to the iteration path (see "Iteration: existing analysis_plan.md" below).
3. **Standalone .duckdb file** — if the user points to a `.duckdb` file instead of a named pipeline, connect with an explicit destination: `dlt.pipeline(pipeline_name="adhoc", destination=dlt.destinations.duckdb("<path>"))`. Then proceed normally — `pipeline.dataset()` works the same way.

## Detect intent

**High-intent** — the user has a specific question (passed as argument, or in their message):
- Skip broad profiling. Schema scan is enough to plan a chart.
- **One chart per invocation.** If the user asks multiple questions, pick the first one. Save the rest as `[ ]` pending questions in analysis_plan.md — they'll be charted in subsequent iterations.
- Go directly to: Connect → Schema scan → Plan chart → Write code → Output analysis_plan.md

**Low-intent** — the user wants to explore without a specific question ("explore my data", "what can I learn?"):
- Broad profiling helps surface what's interesting.
- Go to: Connect → Broad profiling → Generate candidate questions → User picks → Plan chart → Write code → Output analysis_plan.md

## Iteration: existing analysis_plan.md

If `*_<pipeline_name>_analysis_plan.md` already exists (glob for any date prefix; pick most recent): read it, skip Steps 1–2 entirely, and ask for the next question (or present remaining `[ ]` questions). Plan one chart, append as `## Chart N`, hand off to `build-notebook`. See the full iteration loop in `workflow.md`.

## Step 1: Connect to pipeline

Use the dlt MCP tools as the primary discovery path:

1. **`list_pipelines`** — discover available pipelines. If multiple exist and target is ambiguous, ask the user and stop.
2. **`list_tables`** — enumerate tables in the selected pipeline.
3. **`get_table_schema`** — fetch column names and types for relevant tables.

If MCP tools are unavailable, fall back to Python:
```python
import dlt
pipeline = dlt.attach("<pipeline_name>")
dataset = pipeline.dataset()
dataset.row_counts().df()
```

Follow data access patterns in `references/dlt-relation-api.md`.

## Step 2: Schema scan (high-intent) or Broad profiling (low-intent)

### High-intent: Schema scan only

Collect table names, column names, and column types. This is enough to plan a chart for a specific question. No row counts, no stats, no anomaly detection.

Use `list_tables` + `get_table_schema` MCP tools (or `table.columns_schema` in Python).

### Low-intent: Broad profiling

Profile all tables relevant to the user's domain:

1. **Row counts** — use `get_row_counts` MCP tool or `dataset.row_counts().df()`.
2. **Schemas** — use `get_table_schema` MCP tool or `table.columns_schema`.
3. **Per-column stats** — cardinality, null rate, min/max for numeric/temporal columns. Use `execute_sql_query` MCP tool or `.to_ibis()` with group_by/aggregate.
4. **Anomalies** — flag columns with >50% nulls, single-value columns, suspicious distributions.
5. **PII detection** — flag columns whose names or sample values suggest personally identifiable information (email, phone, ssn, address, ip_address, full names).
6. **For 1-2 tables**, profile inline. **For 3+ tables**, profile in parallel using subagents (one per table, all spawned in the same message).

## Step 3: Generate questions (low-intent only)

From the profiling evidence, infer 5-10 plain-language business questions the data can answer. Present as multi-select:

```
question: "What questions interest you? (Pick all — I'll chart one at a time)"
multiSelect: true
options:
  - label: "How has order revenue changed over time?"
    description: "orders table — monthly/weekly trends using created_at + amount"
  - label: "Which categories generate the most revenue?"
    description: "orders table — group by category, sum amount"
  - label: "Other"
    description: "Describe your own question"
```

Avoid PII-flagged columns as chart dimensions or metrics.

## Step 4: Plan chart (one only)

Plan exactly **one** chart per invocation. Do not batch multiple charts — the iteration loop handles additional charts.

For the user's question (from argument or selection), decide:
- **Source table(s)** and which columns to use
- **Chart type** based on question structure:
  - Trend over time → **line chart**
  - Comparison across categories → **bar chart**
  - Relationship between two metrics → **scatter plot**
  - Parts of a whole → **stacked bar or treemap**
  - Distribution → **histogram or box plot**
- **Metric** (what to measure) and **grouping** (how to slice)
- **Time grain** if temporal (daily, weekly, monthly)

### Data gap check

If the columns needed for the question don't exist in any table:
- Tell the user: "The data doesn't have [missing column/concept]. You'd need to add this to your pipeline."
- Record the gap in analysis_plan.md under `## Data Gaps`.
- Suggest handoff to **rest-api-pipeline** toolkit if the user wants to extend the pipeline.
- Do not plan a chart for a question with missing data.

### Confirm the spec

Present the planned chart for confirmation:

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
Source: orders table
"Total order revenue over time, aggregated monthly"
```

If "Adjust", ask one targeted follow-up — don't re-run the full interview.

## Step 5: Write validated code

After the spec is confirmed, generate both ibis query and altair chart code.

### ibis query

```python
t = dataset["orders"].to_ibis()
monthly = (
    t.mutate(month=t.created_at.truncate("M"))
    .group_by("month")
    .aggregate(revenue=t.amount.sum())
    .order_by("month")
    .limit(1000)
)
```

Rules:
- Use `dataset["table"].to_ibis()` to get ibis expressions (see `dlt-relation-api` rule)
- Execute back through the dataset: `dataset(expr).df()`
- Apply development row cap (see row-cap policy in `workflow.md`)
- Use exact column names from the schema

### altair chart

```python
alt.Chart(df).mark_line().encode(
    x="month:T",
    y="revenue:Q",
    tooltip=["month:T", "revenue:Q"]
).properties(title="Monthly Revenue Trend")
```

Rules:
- Use altair type encodings (`:T` temporal, `:Q` quantitative, `:N` nominal, `:O` ordinal)
- Always include tooltip
- Set a descriptive title

Altair encoding docs: https://altair-viz.github.io/user_guide/encodings/channels.html

### Sanity check

Before writing to analysis_plan.md, verify:
- Does the ibis query produce the columns referenced in the altair chart?
- Does the aggregation grain match the chart type (e.g., monthly for a monthly trend)?
- Does the chart actually answer the user's question?

## Step 6: Output analysis_plan.md

Write or append to `<date>_<pipeline_name>_analysis_plan.md` (use today's date in `YYYY-MM-DD` format). See `references/analysis-plan-format.md` for the full template.

The file has these sections:
- **Connection** — pipeline name, dataset, destination type
- **Profile Summary** — table/column/row overview with anomaly and PII notes
- **Questions** — `[x]` charted, `[ ]` pending
- **Data Gaps** — columns needed but missing from schema
- **Chart N** — question, type, ibis query block, altair chart block

For **high-intent** path: Profile Summary may have minimal info (table/column names only). That's fine.

For **low-intent** path: Profile Summary includes row counts, anomaly notes, and PII flags.

Mark the charted question with `[x]` in the Questions list. Remaining `[ ]` questions are available for the next iteration.

## Handoff

After writing analysis_plan.md, hand off to `build-notebook` with the analysis_plan.md path. Tell the user:

"Analysis plan written to `<date>_<pipeline_name>_analysis_plan.md`. Ready to build the notebook — invoking `build-notebook`."

## Troubleshooting

### Pipeline not found
`dlt.attach("<name>")` raises `PipelineNotFound`.
1. Run `list_pipelines` MCP tool to see available pipelines.
2. Check spelling — pipeline names are case-sensitive.
3. If the user has a standalone `.duckdb` file, use `dlt.pipeline(..., destination=dlt.destinations.duckdb("<path>"))`.

### MCP tools unavailable
If `list_pipelines` or `list_tables` return connection errors:
1. Fall back to Python path (`dlt.attach` / `dlt.pipeline`).
2. Tell the user the MCP server may not be running.

### Empty tables / no data loaded
If row counts are all zeros:
1. Confirm pipeline has been run: `dlt pipeline <name> info`.
2. Tell user: "This pipeline has no loaded data yet. Run the pipeline first."

### ibis expression errors
If `.to_ibis()` raises errors:
1. Fall back to raw SQL via `dataset("SELECT ...")`.
2. Check that `ibis-framework[duckdb]` is installed.

## Example

**User says:** "What's the revenue trend in my orders pipeline?"

**Actions (high-intent path):**
1. `list_pipelines` → finds `orders_pipeline`
2. `list_tables` → `orders`, `customers`, `orders__items`
3. `get_table_schema` for `orders` → columns: id, amount, created_at, category, customer_id
4. Plan chart: line chart, x=created_at (monthly), y=sum(amount)
5. Confirm with user → "Yes"
6. Write ibis query + altair chart code
7. Output `2026-03-10_orders_pipeline_analysis_plan.md` with Chart 1

**Result:** Analysis plan with connection info, minimal profile, one charted question with validated code. Hand off to `build-notebook`.

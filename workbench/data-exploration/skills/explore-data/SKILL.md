---
name: explore-data
argument-hint: "[pipeline-name] [question]"
description: This skill should be used when the user asks to "explore my data", "what can I learn from this pipeline", "what's the revenue trend", "show me charts", "visualize my pipeline", "analyze my data", "profile data quality", "what questions can I ask about my data", "map my data to business concepts", or wants to explore, profile, analyze, or chart data from a dlt pipeline. Connects to a pipeline, profiles tables or scans schema, plans charts with ibis + altair code, and writes an analysis_plan.md artifact. Do NOT use for building or fixing pipelines (use rest-api-pipeline toolkit), deploying pipelines (use dlthub-runtime toolkit), or assembling the marimo notebook from an analysis plan (use build-notebook).
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

See `workflow.md` for high-intent vs low-intent definitions. **One chart per invocation** — if the user asks multiple questions, pick the first one and save the rest as `[ ]` pending questions.

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

From the profiling evidence, infer 5-10 plain-language business questions the data can answer. Present as multi-select with table/column hints for each option. Always include an "Other" option for custom questions.

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

Show the chart spec and ask for confirmation or adjustment. Use this format:

```
Chart: <title>
Type: <chart type>
X: <table.column> (<grain>)
Y: <aggregation>(table.column)
Source: <table>
"<one-line description>"
```

If "Adjust", ask one targeted follow-up — don't re-run the full interview.

## Step 5: Write validated code

After the spec is confirmed, generate the SQL query and altair chart code.

### Query rules (SQL-first)
- Default to SQL: `dataset("SELECT ... FROM table_name ...").df()`
- Chart queries produce aggregated data — always GROUP BY and aggregate rather than selecting raw rows
- Use ibis (`dataset["table"].to_ibis()`) only for complex joins or computed columns
- Use exact column names from the schema — verify against `get_table_schema`
- See `references/dlt-relation-api.md` for full API reference

### altair rules
- Use altair type encodings (`:T` temporal, `:Q` quantitative, `:N` nominal, `:O` ordinal)
- Always include tooltip
- Set a descriptive title
- Altair encoding docs: https://altair-viz.github.io/user_guide/encodings/channels.html

### Sanity check
- Does the SQL query produce the columns referenced in the altair chart?
- Does the aggregation grain match the chart type (e.g., monthly for a monthly trend)?
- Does the chart actually answer the user's question?

## Step 6: Output analysis_plan.md

Write or append to `<date>_<pipeline_name>_analysis_plan.md` (use today's date in `YYYY-MM-DD` format). See `references/analysis-plan-format.md` for the full template.

The file has these sections:
- **Connection** — pipeline name, dataset, destination type
- **Profile Summary** — table/column/row overview with anomaly and PII notes
- **Questions** — `[x]` charted, `[ ]` pending
- **Data Gaps** — columns needed but missing from schema
- **Chart N** — question, type, SQL query block, altair chart block

For **high-intent** path: Profile Summary may have minimal info (table/column names only). That's fine.

For **low-intent** path: Profile Summary includes row counts, anomaly notes, and PII flags.

Mark the charted question with `[x]` in the Questions list. Remaining `[ ]` questions are available for the next iteration.

## Handoff — MUST propose notebook

After writing or appending to analysis_plan.md, you **MUST** propose building the notebook. Never end a session that produced a chart without this step.

Tell the user the plan was updated, then ask: "Ready to build the notebook — shall I invoke `build-notebook`?" If they agree, invoke it. If they decline, remind them they can run `build-notebook` later.

## Troubleshooting

- **Pipeline not found** — check spelling (case-sensitive), run `list_pipelines`, or use explicit `.duckdb` path via `dlt.pipeline(..., destination=dlt.destinations.duckdb("<path>"))`.
- **MCP tools unavailable** — run `uv run dlt ai status` to diagnose. If the MCP server is not running or misconfigured, attempt to fix it (e.g., `dlt ai init`). Only fall back to Python path (`dlt.attach` / `dlt.pipeline`) if MCP cannot be restored.

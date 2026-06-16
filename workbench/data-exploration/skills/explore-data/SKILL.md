---
name: explore-data
argument-hint: "[pipeline-name] [question]"
description: This skill should be used when the user asks to "explore my data", "what can I learn from this pipeline", "what's the revenue trend", "show me charts", "visualize my pipeline", "analyze my data", "profile data quality", "what questions can I ask about my data", "map my data to business concepts", or wants to explore, profile, analyze, or chart data from a dlt pipeline. Connects to a pipeline, profiles tables or scans schema, plans charts with ibis + altair code, and writes an analysis_plan.md artifact. Do NOT use for building or fixing pipelines (use rest-api-pipeline toolkit), deploying pipelines (use dlthub-platform toolkit), or assembling the marimo notebook from an analysis plan (use build-notebook).
---

# Explore data and plan charts

Connect to a dlt pipeline, understand the data, and plan charts. Outputs a `<date>_<pipeline_name>_analysis_plan.md` artifact that `build-notebook` consumes. Use today's date in `YYYY-MM-DD` format (e.g., `2026-03-10`).

## Batch vs interactive — pick ONE mode up front

This is the biggest driver of how fast the session runs. Each round-trip to the user or a re-invocation costs real time, so default to batch unless the user is clearly exploring live.

- **Batch mode (DEFAULT)** — the user named a count or set of questions ("3 charts", "revenue and signups over time", "all of them"), or this is a non-interactive run. Plan **all** charts in a single pass, write the whole `analysis_plan.md` in **one** Write, and hand off to `build-notebook` **once**. Do not loop one chart at a time.
- **Interactive mode** — the user is exploring open-endedly and wants to react to each chart before the next. Only then plan one chart, propose the notebook, and iterate. This is the slow path; use it only when the user asked for it.

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline name. If omitted, infer from session context. If ambiguous, ask the user and stop.
- `question` (optional, after `--`): a specific business question (e.g., `-- what's the revenue trend?`)

## Session context — skip redundant work

Before discovery, check what's already available:

1. **Pipeline already known** — if `pipeline-name` was passed via `$ARGUMENTS` or the session already has a pipeline context (e.g., arriving from `rest-api-pipeline` after `validate-data` or `view-data`), skip `list_pipelines` and go straight to schema discovery (Step 1.2).
2. **Existing analysis_plan.md** — if `*_analysis_plan.md` exists, skip to the iteration path (see "Iteration: existing analysis_plan.md" below).
3. **Standalone .duckdb file** — if the user points to a `.duckdb` file instead of a named pipeline, connect with an explicit destination: `dlt.pipeline(pipeline_name="adhoc", destination=dlt.destinations.duckdb("<path>"))`. Then proceed normally — `pipeline.dataset()` works the same way.

## Detect intent

See `workflow.md` for high-intent vs low-intent definitions. High-intent = the user has specific question(s); low-intent = open-ended exploration. Either can be run in **batch** or **interactive** mode (see above) — batch is the default.

## Iteration: existing analysis_plan.md

If `*_<pipeline_name>_analysis_plan.md` already exists (glob for any date prefix; pick most recent): read it, **skip Steps 1–2 entirely**, and plan the next chart(s). In interactive mode, ask for the next question or present remaining `[ ]` questions, plan one, append as `## Chart N`, hand off to `build-notebook`. See the full iteration loop in `workflow.md`.

## Step 1–2: Connect and understand the data (first run only)

On the **returning path** (an `analysis_plan.md` already exists) skip this entirely — go to Step 3.

Otherwise:

1. **`list_pipelines`** — only if the pipeline is not already known from `$ARGUMENTS` or session context. If multiple exist and the target is ambiguous, ask the user and stop.
2. Understand the schema with **one** call:
   - **High-intent** — **`export_schema`** (`output_format="yaml"`): all tables, columns, and types. Enough to plan a chart for a specific question; no stats needed.
   - **Low-intent** — **`profile_tables`** from `dlt-profiling-mcp`: schema + row counts + per-column stats + samples for every table in one call. Use this for question generation in Step 3.

For the exact tool arguments, the MCP-unavailable fallback (batched, no chatty per-table loops), and PII/anomaly flagging rules, read **`references/first-run-profiling.md`** — only on the first run, and only if you need the detail. The always-loaded MCP-efficiency rule (`dlthub-workspace.md`) already covers the batching principle.

## Step 3: Generate questions (low-intent only)

If the user already named the question(s), skip generation and go to Step 4. Otherwise, from the profiling evidence infer 5-10 plain-language business questions the data can answer. Present as multi-select with table/column hints for each option; always include an "Other" option. In batch mode the user can pick several at once.

Avoid PII-flagged columns as chart dimensions or metrics.

## Step 4: Plan the chart(s)

In **batch mode**, plan **all** confirmed questions in this one pass (Steps 4–6 once for the whole set). In **interactive mode**, plan exactly one chart and let the iteration loop handle the rest.

For each question (from argument or selection), decide:
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

Show the chart spec(s) and ask for confirmation or adjustment. In batch mode show **all** specs at once in a single message and get one confirmation for the set — do not confirm one at a time. Use this format per chart:

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
- Use exact column names from the schema already in context (the `export_schema` / `profile_tables` output) — no extra schema calls
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

Write `<date>_<pipeline_name>_analysis_plan.md` (use today's date in `YYYY-MM-DD` format). In **batch mode** write the whole file — Connection, Profile Summary, all `## Chart N` blocks — in a **single Write call**; do not append one chart at a time. In interactive/returning mode, append the new `## Chart N`. See `references/analysis-plan-format.md` for the full template.

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

After writing analysis_plan.md, you **MUST** propose building the notebook. Never end a session that produced a chart without this step. In batch mode propose **once**, after all charts are written — not per chart.

Tell the user the plan was updated, then ask: "Ready to build the notebook — shall I invoke `build-notebook`?" If they agree, invoke it. If they decline, remind them they can run `build-notebook` later.

## Troubleshooting

- **Pipeline not found** — check spelling (case-sensitive), run `list_pipelines`, or use explicit `.duckdb` path via `dlt.pipeline(..., destination=dlt.destinations.duckdb("<path>"))`.
- **MCP tools unavailable** — run `uv run dlthub ai status` to diagnose. If the MCP server is not running or misconfigured, attempt to fix it (e.g., `dlthub ai init`). Only fall back to Python path (`dlt.attach` / `dlt.pipeline`) if MCP cannot be restored.

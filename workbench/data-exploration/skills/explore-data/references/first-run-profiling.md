# First-run connection and profiling

Read this only on the **first run** for a pipeline (no `analysis_plan.md` yet) when you need the detail behind Steps 1–2. The returning path skips all of this.

## Connection

Use the dlthub MCP tools as the primary discovery path. If MCP tools are unavailable, fall back to Python:

```python
import dlt

pipeline = dlt.attach("<pipeline_name>")
dataset = pipeline.dataset()
dataset.row_counts().df()
```

Follow data access patterns in `references/dlt-relation-api.md`.

## High-intent: schema scan only

One `export_schema` call (`output_format="yaml"`) returns all table names, column names, and types — enough to plan a chart for a specific question. No row counts, no stats, no anomaly detection. Do not enumerate with `list_tables` + per-table `get_table_schema`; that costs N+1 calls for the same information.

## Low-intent: broad profiling

Profile all tables relevant to the user's domain.

**Primary path — one call**: use **`profile_tables`** from `dlt-profiling-mcp` (pass `pipeline_name`, optionally `table_names`). It returns, for every table at once: schema, row count, per-column stats (null count, distinct count, min/max), and sample rows. One MCP call replaces the entire profiling sweep — never follow it with `get_table_schema`, `get_row_counts`, or per-column `execute_sql_query` calls. The call is capped at 20 tables (the rest come back in `skipped_tables`) — on large pipelines pass `table_names` with the tables relevant to the user's domain instead of profiling everything.

**Fallback** (if `dlt-profiling-mcp` is not connected), still batch aggressively:

1. **Row counts** — one `get_row_counts` call (all tables).
2. **Schemas** — one `export_schema` call (all tables).
3. **Per-column stats** — **one `execute_sql_query` per table** computing null counts, distinct counts, and min/max for **all columns in a single SELECT** (e.g. `SELECT COUNT(*), COUNT(*) - COUNT(col_a), COUNT(DISTINCT col_a), MIN(col_b), MAX(col_b), ... FROM t`). Never one query per metric or per column.
4. **Samples** — `preview_table` for each table, all calls issued in a single message so they run in parallel.

## Flagging (from the returned stats and samples — no extra calls)

- **Anomalies** — flag columns with >50% nulls, single-value columns, suspicious distributions.
- **PII detection** — flag columns whose names or sample values suggest personally identifiable information (email, phone, ssn, address, ip_address, full names). Avoid PII-flagged columns as chart dimensions or metrics.
- **Degenerate temporal columns** — if a date/timestamp column has ≤2 distinct buckets at the chart's grain (e.g. all rows in one month), a "trend over time" chart renders as a single point. Note it and prefer a different question or grain.

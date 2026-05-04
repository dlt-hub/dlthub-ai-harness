---
name: review-data-quality
argument-hint: "[pipeline-name]"
description: Use when the user asks to "review data quality results", "what failed", "show me DQ results", "analyze check results", "investigate DQ failures", or wants to understand check and metric outcomes from a pipeline run. Do NOT use to run new checks (use run-data-quality).
---

# Review data quality results

Read DQ check and metric results incrementally, surface failures with remediation suggestions, and recommend next steps.

Reference: [dlt data quality docs](https://dlthub.com/docs/hub/features/quality/data-quality)

## Session context — carry-over from run-data-quality

Expected from prior steps:
- Confirmed pipeline name
- Tables with checks and metrics applied
- Run outcome (success / failures detected) and any pre-identified failing tables

**Incremental querying rule:** always start with table-level aggregates. Load row-level detail only when the user explicitly asks for it or when a failure needs drill-down to diagnose root cause. Never load the entire DQ result set in one query.

## Steps

### 1. Get table row counts

Use the `get_row_counts` MCP tool for the confirmed pipeline to establish a baseline: how many rows are in each table. This is the first sanity check — if a table has zero rows or an unexpectedly low count, that is itself a finding, independent of checks.

Present compactly:

```
Row counts — pipeline "my_pipeline":
  orders        12,450 rows
  customers      3,102 rows
  order_items   38,901 rows
  products         284 rows
```

Flag any table where the count is 0 or significantly lower than expected (if prior runs exist, compare with `latest_loaded_at` metric).

### 2. Build a table-level check summary

The DQ checks table is `_dlt_checks`, located within the pipeline's destination dataset. The physical path depends on the destination — for DuckDB it is `{dataset_name}._dlt_checks` (e.g., `navit._dlt_checks`). If the exact path is unknown, call `list_tables` MCP first to locate it.

Schema columns: `table_name`, `check_qualified_name`, `row_count`, `success_count`, `success_rate` (0.0–1.0; 1.0 = all rows passed).

For each table, query using `execute_sql_query` MCP:

```sql
SELECT
    check_qualified_name,
    row_count,
    success_count,
    success_rate
FROM _dlt_checks
WHERE table_name = '<table>'
ORDER BY success_rate ASC
```

A check passes when `success_count = row_count` (equivalently `success_rate = 1.0`).

Present one table at a time as results come in:

```
Table: orders
  ✓ is_unique("id")                 — passed
  ✓ is_not_null("customer_id")      — passed
  ✗ case("amount >= 0")             — 3 rows failed
  ✗ is_not_null("status")           — 42 rows failed

Table: customers
  ✓ is_unique("id")                 — passed
  ✗ is_unique("email")              — 7 duplicates found
```

Do not move to metrics until all tables have been summarised this way.

### 3. Read metric results

For each table, query metric results using `execute_sql_query` MCP. The metrics table is `_dlt_dq_metrics`, in the same destination dataset as `_dlt_checks`:

```sql
SELECT
    table_name,
    column_name,
    metric_name,
    metric_value,
    _dlt_load_id
FROM _dlt_dq_metrics
WHERE table_name = '<table>'
ORDER BY _dlt_load_id DESC
LIMIT 50
```

**Trend detection:** if multiple `_dlt_load_id` values exist for the same metric (i.e. the pipeline has run more than once), compute the delta and flag meaningful changes:

| Metric | Flag condition |
|---|---|
| `null_rate` | Increased by > 5 percentage points vs. previous run |
| `row_count` | Dropped by > 20% vs. previous run |
| `minimum` / `maximum` | Outside historical range (new min/max) |
| `unique_count` | Dropped (potential deduplication or data loss) |

Present metrics alongside the check summary for each table:

```
Table: orders — metrics
  row_count:                12,450   (↑ 450 from last run)
  column.mean("amount"):       82.4  (stable)
  column.minimum("amount"):   -15.0  ⚠ new minimum — negative value (aligns with case() failure)
  column.null_rate("status"):   0.34  ⚠ up from 0.0 last run
```

### 4. Diagnose failures and suggest remediation

For each failing check, classify the failure and suggest a fix. Ask the user one table at a time if there are many failures — do not dump everything at once.

**Classification and remediation table:**

| Failure pattern | Root cause | Suggested action |
|---|---|---|
| `is_not_null` fails on a column that should be required | Source data has gaps / upstream nulls | Filter at source: add `filter(lambda r: r["col"] is not None)` to the resource, or raise a support ticket with the data owner |
| `is_unique` / `is_primary_key` fails | Duplicate records in source or during incremental merge | Check merge key config; add `dlt.mark.make_hints(primary_key="id")` if missing; investigate source deduplication |
| `case("amount >= 0")` fails | Bad values allowed through at source | Add a transformer to reject or flag negative amounts; or relax the check if negatives are valid (refunds) |
| `is_in("status", [...])` fails with new values | Source added a new enum value | Update the allowed set in the check definition — go back to `define-data-quality-checks` |
| `null_rate` trending up | Optional field becoming sparsely populated | Flag to data owner; add `is_not_null` if the field is business-critical |
| `row_count` drop > 20% | Truncation, filter change, or load issue | Use `execute_sql_query` to check `_dlt_loads` for failed jobs; compare with previous load |

For each failure, state the classification and proposed action explicitly before asking the user what to do.

### 5. Drill down on request

If the user asks "show me the failing rows" or "which emails are duplicated":

Use `execute_sql_query` MCP scoped to that specific table and column — never a full table scan:

```sql
-- Example: find duplicate emails
SELECT email, COUNT(*) AS cnt
FROM customers
GROUP BY email
HAVING COUNT(*) > 1
ORDER BY cnt DESC
LIMIT 20
```

Keep queries narrow: one table, one column, one question at a time. Cap results at 20–50 rows unless the user asks for more.

### 6. Final summary and next steps

After all tables are reviewed, present a concise overall verdict:

```
DQ review complete — pipeline "my_pipeline"

  Checks:   8 passed / 3 failed
  Metrics:  2 anomalies flagged (null_rate on status, new minimum on amount)

Failures needing action:
  1. orders.status — 42 null rows (source gap)
  2. orders.amount — 3 negative values (check too strict or refunds allowed?)
  3. customers.email — 7 duplicates (merge key issue)
```

Then recommend one of these next steps based on what was found:

- **Checks need adjustment** (check was too strict, enum values changed) → loop back to `define-data-quality-checks` with the specific checks pre-targeted
- **Source data has real problems** → hand over to **rest-api-pipeline** toolkit (`adjust-endpoint` or `new-endpoint`) to fix the data at the source
- **Anomalies need deeper investigation** → hand over to **data-exploration** toolkit (`explore-data`) with the table name and failing column already in context
- **Everything looks good** → hand over to **dlthub-runtime** toolkit (`setup-runtime`) to deploy the pipeline with continuous DQ monitoring

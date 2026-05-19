---
name: review-data-quality
argument-hint: "[pipeline-name]"
description: Use when the user asks to "review data quality results", "what failed", "show me data quality results", "analyze check results", "investigate data quality failures", or wants to understand check and metric outcomes from a pipeline run. Do NOT use to run new checks (use run-data-quality).
---

# Review data quality results

Read data quality check and metric results incrementally, surface failures with remediation suggestions, and recommend next steps.

Reference: [dlt data quality docs](https://dlthub.com/docs/hub/features/quality/data-quality)

## Session context — carry-over from run-data-quality

Expected from prior steps:
- Confirmed pipeline name
- Tables with checks and metrics applied
- Run outcome (success / failures detected) and any pre-identified failing tables

**Incremental querying rule:** always start with table-level aggregates. Load row-level detail only when the user explicitly asks for it or when a failure needs drill-down to diagnose root cause. Never load the entire data quality result set in one query.

## Quick summary mode

If this skill is invoked directly (no carry-over context from `run-data-quality`), lead with a compact snapshot before the full review flow. Read results using the dlt library:

```python
import dlt
from dlt.hub import data_quality as dq  # https://dlthub.com/docs/hub/features/quality/data-quality

pipeline = dlt.attach(pipeline_name="<name>")
results = dq.read_check(pipeline.dataset())
rows = results.fetchall()
cols = results.columns
```

Group by `table_name` and present a compact verdict:

```
Latest data quality snapshot — pipeline "my_pipeline"

  orders      3 checks: ✓ ✓ ✗  (1 failure)
  customers   2 checks: ✓ ✓
  products    2 checks: ✓ ✓

1 failure detected. Want to drill into metrics and failures, or is this enough?
```

If the user says "that's enough", stop here. If they want to go deeper, continue to the full review steps below.

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

Read check results using internal dlt functionality:

```python
import dlt
from dlt.hub import data_quality as dq  # https://dlthub.com/docs/hub/features/quality/data-quality

pipeline = dlt.attach(pipeline_name="<name>")
results = dq.read_check(pipeline.dataset(), table="<table>")
rows = results.fetchall()
cols = results.columns
```

**`_dlt_checks` accumulates one row per check per run** — historical rows are kept for auditability but make it noisy to answer "did the current checks pass?". If `dq.read_check()` returns multiple rows per check (multiple `_dlt_load_id` values), scope to the latest by filtering on `max(_dlt_load_id)` before presenting. Do this for each table separately.

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

For each table, read metric results using the dlt library:

```python
import dlt
from dlt.hub import data_quality as dq  # https://dlthub.com/docs/hub/features/quality/data-quality

pipeline = dlt.attach(pipeline_name="<pipeline-name>")

# dataset-level metric (e.g. load_row_count, latest_loaded_at)
results = dq.read_metric(pipeline.dataset(), metric="<metric-name>")

# table-level metric (e.g. row_count)
results = dq.read_metric(pipeline.dataset(), table="<table>", metric="<metric-name>")

# column-level metric (e.g. null_rate, mean)
results = dq.read_metric(pipeline.dataset(), table="<table>", column="<col>", metric="<metric-name>")

rows = results.fetchall()
cols = results.columns
```

`metric` is required — make one call per metric name. Consume with `.fetchall()` and `.columns`. Fields: `table_name`, `column_name`, `metric_name`, `metric_value`, `_dlt_load_id`.

**Profile A only.** `dq.read_metric()` reads from schema hints written by `@dq.with_metrics`. Calling it in a Profile B context (no decorators, no schema hints) raises `StopIteration` or `KeyError` with no useful error message — skip this step entirely for Profile B.

**Trend detection:** if multiple `_dlt_load_id` values exist for the same metric (i.e. the pipeline has run more than once), compute the delta per metric and ask the user to set alert thresholds before flagging:

```
I can compare these metrics against the previous run and flag meaningful changes.
What thresholds should I use?

  null_rate      — flag if increased by more than ___% points
  row_count      — flag if dropped by more than ___%
  minimum/maximum — flag if outside historical range? (yes/no)
  unique_count   — flag if dropped? (yes/no)

Say "skip" to show all deltas without filtering.
```

Wait for the user's answer. If they say "skip", present all deltas with no threshold filtering. Otherwise apply their stated thresholds when deciding what to flag.

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
Data quality review complete — pipeline "my_pipeline"

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
- **Everything looks good** → hand over to **dlthub-platform** toolkit (`setup-runtime`). Use the execution context carried over from `run-data-quality`:
  - If checks are embedded in the pipeline via decorators: deploy the pipeline script — checks run automatically on every load
  - If checks run via a standalone script: deploy that script as a separate scheduled job, passing the script path and pipeline name to `setup-runtime`

  If the execution context was not carried over, ask: "Are your checks part of the pipeline code, or do you run them separately via a script?"

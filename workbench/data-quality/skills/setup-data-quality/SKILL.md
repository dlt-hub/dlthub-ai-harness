---
name: setup-data-quality
argument-hint: "[pipeline-name]"
description: This skill should be used when the user asks to "set up data quality", "enable data quality checks", "add DQ to my pipeline", "validate my pipeline data", "I want to check data quality", "check my tables for issues", "set up a DQ contract", or wants to start any data quality workflow on a dlt pipeline. Inspects the pipeline schema, surfaces auto-detected check candidates from schema hints, and enables the DQ flag on the pipeline. Do NOT use for exploring or charting data (use data-exploration toolkit), running existing checks (use run-data-quality), or reviewing results (use review-data-quality).
---

# Setup data quality

Orient the user, inspect what data exists, and prepare the pipeline for DQ.

Reference: [dlt data quality docs](https://dlthub.com/docs/hub/features/quality/data-quality)

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline name. If omitted, list pipelines and ask the user to choose.

## Session context — skip redundant work

Before any discovery step, check what is already known:

1. **Pipeline already known** — if `pipeline-name` was passed via `$ARGUMENTS` or the session already has a pipeline context (arriving from `rest-api-pipeline` after `validate-data`, or from `transformations` after `validate-transformed-data`), skip `list_pipelines` discovery.
2. **License already confirmed** — if the session already verified the `dlthub.data_quality` license scope, skip step 1.

## Steps

### 1. Verify license

The `dlthub.data_quality` scope is required to run checks. Check for it before the user invests time defining checks — if it becomes a paid scope in the future, the user should know up front.

Run:

```python
import dlt
dlt.config["license"]  # or inspect ~/.dlt/secrets.toml
```

Simpler: attempt a dry import of the licensed function:

```python
from dlthub.common.license.license import get_license
license = get_license()
scopes = license.scopes if license else []
print(scopes)
```

If `dlthub.data_quality` is not in the scopes, tell the user:

```
Running data quality checks requires the dlthub.data_quality license scope.
This is currently available as a free trial. To proceed, run:

    dlt license issue dlthub.data_quality

You will be asked to agree to the dltHub EULA before the license is issued.
```

Wait for the user to confirm they've run the command before continuing. Do not issue the license yourself.

Once the license is confirmed (scopes include `dlthub.data_quality`), continue.

### 3. Confirm pipeline

Use the `list_pipelines` MCP tool to list all local dlt pipelines. If `pipeline-name` was passed, verify it appears in the list. If it does not exist, stop and tell the user:

```
Pipeline "<name>" not found locally. Available pipelines: <list>.
Run the pipeline at least once before setting up data quality.
```

If `pipeline-name` was not provided, present the list and ask the user to pick one. Wait for confirmation before continuing.

**IMPORTANT: Confirm the exact pipeline name before any further MCP calls.** A wrong name causes all subsequent schema lookups to fail silently or return empty results.

### 4. Discover tables

Use the `list_tables` MCP tool for the confirmed pipeline. Collect the table names and column counts. Skip `_dlt_*` system tables.

Present a compact list to the user:

```
Pipeline "my_pipeline" — 4 tables:
  orders        (12 columns)
  customers     (8 columns)
  order_items   (5 columns)
  products      (9 columns)
```

If there are no non-system tables, stop:

```
No data tables found in pipeline "<name>". Run the pipeline at least once to load data.
```

### 5. Inspect schema and auto-detect check candidates

For each table from step 4, call `display_schema` MCP tool. Read the column-level hints returned (type, `nullable`, `unique`).

Map hints to DQ check candidates using this table:

| Schema hint | Auto-detected check |
|---|---|
| `primary_key: true` | `dq.checks.is_primary_key("col")` |
| `nullable: false` | `dq.checks.is_not_null("col")` |
| `unique: true` | `dq.checks.is_unique("col")` |

**Known issue:** `dq.checks.is_primary_key()` is not yet fully implemented — the SQL template hardcodes `value` instead of the actual column name (marked `# TODO parameterize` in the source). It will raise a `LineageFailedException` at runtime. Substitute `dq.checks.is_unique("col")` until the library completes the implementation.

Collect candidates per table. Ignore columns with no actionable hints.

### 6. Present summary to the user

Present a summary table. Do not ask for decisions yet — that happens in `define-data-quality-checks`. This step is read-only.

```
Schema summary for pipeline "my_pipeline":

Table: orders
  id           bigint    → is_primary_key("id")
  customer_id  bigint    → is_not_null("customer_id")
  status       text      (no hint)
  amount       float     (no hint)

Table: customers
  id           bigint    → is_primary_key("id"), is_unique("id")
  email        text      → is_not_null("email")
  ...

(2 more tables — no auto-detected candidates)
```

**For tables with no auto-detected candidates**, do not skip them. Ask the user directly about business intent for each such table:

```
Table "wallets" has no schema hints. A few quick questions:
  - Which column(s) identify a unique record? (e.g., id, transaction_id)
  - Are there any columns that must always have a value?
  - Any value constraints? (e.g., "amount must be >= 0", "status must be one of X/Y/Z")

Say "none" or "skip" to move on without adding checks for this table.
```

Record the user's answers as free-form notes — they will be passed to `define-data-quality-checks` as business intent. Do not map to specific checks yet; that happens in define.

## Output and handover

Pass the following context to `define-data-quality-checks`:
- Confirmed pipeline name
- Table list (names + column counts)
- Auto-detected check candidates per table (from schema hints)
- Business intent per table (free-form notes from Q&A on hint-less tables; omit tables where user said "skip")

```
Schema inspected. Ready to define checks.
Moving to define-data-quality-checks →
```
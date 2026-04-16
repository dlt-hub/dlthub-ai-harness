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
2. **DQ already enabled** — if the session indicates `dq.enable_data_quality()` was already called in a prior run, skip step 4 and go straight to the handover.

## Steps

### 1. Confirm pipeline

Use the `list_pipelines` MCP tool to list all local dlt pipelines. If `pipeline-name` was passed, verify it appears in the list. If it does not exist, stop and tell the user:

```
Pipeline "<name>" not found locally. Available pipelines: <list>.
Run the pipeline at least once before setting up data quality.
```

If `pipeline-name` was not provided, present the list and ask the user to pick one. Wait for confirmation before continuing.

**IMPORTANT: Confirm the exact pipeline name before any further MCP calls.** A wrong name causes all subsequent schema lookups to fail silently or return empty results.

### 2. Discover tables

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

### 3. Inspect schema and auto-detect check candidates

For each table from step 2, call `display_schema` MCP tool. Read the column-level hints returned (type, `primary_key`, `nullable`, `unique`).

Map hints to DQ check candidates using this table:

| Schema hint | Auto-detected check |
|---|---|
| `primary_key: true` | `dq.checks.is_primary_key("col")` |
| `nullable: false` | `dq.checks.is_not_null("col")` |
| `unique: true` | `dq.checks.is_unique("col")` |

Collect candidates per table. Ignore columns with no actionable hints.

### 4. Present summary to the user

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

If a table has no hints at all, note it briefly but do not skip it — the user may still want manual checks on it.

### 5. Enable DQ on the pipeline

> **Dependency note:** `dq.enable_data_quality()` requires `dlt.hub`. If the import fails, skip this step, note it to the user, and proceed to the handover — the check scaffolding in `define-data-quality-checks` works independently. No structural rework needed once the API lands.

Run the following in a Python snippet:

```python
import dlt
from dlt.hub import data_quality as dq  # https://dlthub.com/docs/hub/features/quality/data-quality

pipeline = dlt.attach(pipeline_name="<pipeline-name>")
dq.enable_data_quality(pipeline)
print("DQ enabled — flag persisted in pipeline state.")
```

Confirm success with the user:

```
DQ enabled on pipeline "my_pipeline". The flag is persisted in pipeline state across runs.
```

If the import is unavailable, say:

```
dlt.hub is not yet available in this environment — DQ flag not set.
You can still define and scaffold checks now; enable_data_quality() can be wired in once the API lands.
```

## Output and handover

Pass the following context to `define-data-quality-checks`:
- Confirmed pipeline name
- Table list (names + column counts)
- Auto-detected check candidates per table (from step 3)

Hand over immediately — do not ask the user for confirmation again unless step 5 failed:

```
Schema inspected. Ready to define checks.
Moving to define-data-quality-checks →
```
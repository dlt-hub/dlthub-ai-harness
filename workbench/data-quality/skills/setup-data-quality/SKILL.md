---
name: setup-data-quality
argument-hint: "[pipeline-name]"
description: Use when the user asks to "set up data quality", "enable data quality checks", "add data quality to my pipeline", "validate my pipeline data", "I want to check data quality", "check my tables for issues", or wants to start any data quality workflow on a dlt pipeline. Do NOT use for exploring or charting data (use data-exploration toolkit), running existing checks (use run-data-quality), or reviewing results (use review-data-quality).
---

# Setup data quality

Orient the user, inspect what data exists, and prepare the pipeline for data quality.

Reference: [dlt data quality docs](https://dlthub.com/docs/hub/features/quality/data-quality)

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline name. If omitted, list pipelines and ask the user to choose.

## Session context — skip redundant work

Before any discovery step, check what is already known:

1. **Pipeline already known** — if `pipeline-name` was passed via `$ARGUMENTS` or the session already has a pipeline context (arriving from `rest-api-pipeline` after `validate-data`, or from `transformations` after `create-transformation`), skip `list_pipelines` discovery.
2. **License already confirmed** — if the session already verified the `dlthub.data_quality` license scope, skip step 1.

## Steps

### 1. Verify license

The `dlthub.data_quality` scope is required to run checks. Check for it before the user invests time defining checks — if it becomes a paid scope in the future, the user should know up front.

Run the CLI command:

```
dlt license info
```

This prints the installed license and its scopes. Check that `dlthub.data_quality` appears in the `Scopes` field.

If the command errors ("no license found") or `dlthub.data_quality` is not in the scopes, tell the user:

```
Running data quality checks requires the dlthub.data_quality license scope.
This is currently available as a free trial. To proceed, run:

    dlt license issue dlthub.data_quality

Important: run this command from the same working directory where your pipeline
runs. The license is tied to that directory — issuing it elsewhere will cause
checks to fail with a license error at runtime.

You will be asked to agree to the dltHub EULA before the license is issued.
```

Wait for the user to confirm they've run the command before continuing. Do not issue the license yourself.

Once the license is confirmed (scopes include `dlthub.data_quality`), continue.

### 2. Confirm pipeline

Use the `list_pipelines` MCP tool to list all local dlt pipelines.

**If `list_pipelines` returns an empty list**, do not stop silently. Fall back to the CLI:

```
dlt pipeline --list-pipelines
```

If the CLI also returns nothing, tell the user:

```
No pipelines found in this workspace. This usually means the pipeline was run
from a different directory. Please provide the pipeline name directly, or
navigate to the directory where the pipeline was run and restart.
```

Then ask the user to provide the pipeline name manually and continue once they do.

**If pipelines are found:**

- If `pipeline-name` was passed, verify it appears in the list. If it does not, stop and tell the user:

  ```
  Pipeline "<name>" not found. Available pipelines: <list>.
  Run the pipeline at least once before setting up data quality.
  ```

- If `pipeline-name` was not provided, present the list and ask the user to pick one. Wait for confirmation before continuing.

**IMPORTANT: Confirm the exact pipeline name before any further MCP calls.** A wrong name causes all subsequent schema lookups to fail silently or return empty results.

### 3. Discover tables

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

### 4. Inspect schema and auto-detect check candidates

Run a small inline script to generate check candidates directly from the pipeline schema:

```python
import dlt
from dlthub.data_quality.checks._definitions import create_check_hints_from_schema, _check_hints_to_def

pipeline = dlt.attach(pipeline_name="<name>")
hints = create_check_hints_from_schema(pipeline.default_schema)

# Bug workaround: is_primary_key() hardcodes `value` instead of the actual column name
# in its SQL template (dlt-hub/dlthub#397) and raises LineageFailedException at runtime.
# Substitute with is_unique() on the same column until the bug is fixed.
for table_hints in hints["tables"].values():
    for h in table_hints:
        if h["name"] == "is_primary_key":
            h["name"] = "is_unique"
            h["args"] = {"column": h["args"]["columns"][0]}
```

`create_check_hints_from_schema` maps schema column metadata to check candidates:

| Schema hint | Auto-detected check |
|---|---|
| `primary_key: true` | `is_unique("col")` *(substituted — see bug note above)* |
| `nullable: false` | `is_not_null("col")` |
| `unique: true` | `is_unique("col")` |
| `row_key: true` | `is_unique("col")` |

Collect candidates per table. Ignore tables where `hints["tables"]` returns an empty list.

**Important — source of truth:** The schema state, pipeline code, and destination can get out of sync. If the schema already shows `x-dq-checks` metadata (from a previous session or external edit) but the code has no decorators, or vice versa, make this explicit to the user: for Profile A the code is the source of truth (re-running the pipeline overwrites schema hints with whatever the decorators say); for Profile B the `dq.run_checks` call is the source of truth; the `_dlt_checks` destination table reflects only what was last executed.

### 5. Present summary to the user

Present a summary table. Do not ask for decisions yet — that happens in `define-data-quality-checks`. This step is read-only.

```
Schema summary for pipeline "my_pipeline":

Table: orders
  id           bigint    → is_unique("id")
  customer_id  bigint    → is_not_null("customer_id")
  status       text      (no hint)
  amount       float     (no hint)

Table: customers
  id           bigint    → is_unique("id")
  email        text      → is_not_null("email")
  ...

(2 more tables — no auto-detected candidates)
```

**For tables with no auto-detected candidates**, do not skip them — but do not ask about each one individually if there are many.

**If there are 5 or fewer hint-less tables:** ask directly about each:

```
Table "wallets" has no schema hints. A few quick questions:
  - Which column(s) identify a unique record? (e.g., id, transaction_id)
  - Are there any columns that must always have a value?
  - Any value constraints? (e.g., "amount must be >= 0", "status must be one of X/Y/Z")

Say "none" or "skip" to move on without adding checks for this table.
```

**If there are more than 5 hint-less tables:** group them by common name prefix (e.g., `payment_*`, `employee_*`, `order_*`) and ask the user to prioritize first:

```
38 tables have no schema hints. Here are the groups I see:

  payment_*     (8 tables)
  employee_*    (6 tables)
  operator_*    (4 tables)
  invoice_*     (3 tables)
  ... (17 more)

Which group or domain matters most for data quality? I'll ask detailed questions
about those first. Say "all" to go through everything, or name the groups to focus on.
```

Only ask the three detailed questions (unique columns, required columns, value constraints) for the groups the user selects. Record all answers as free-form notes to pass to `define-data-quality-checks`. Do not map to specific checks yet.

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

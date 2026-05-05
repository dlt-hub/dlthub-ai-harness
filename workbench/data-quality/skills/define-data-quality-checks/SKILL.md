---
name: define-data-quality-checks
argument-hint: "[pipeline-name] [table]"
description: Use when the user asks to "define checks", "add validation rules", "what checks should I add", "translate requirements into checks", or wants to map schema hints or business rules to dlt data quality check and metric calls for a specific pipeline or table. Do NOT use to run checks (use run-data-quality) or to set up the pipeline environment (use setup-data-quality).
---

# Define data quality checks

Translate business requirements into concrete dlt data quality checks and metrics, then write them into the pipeline code.

Reference: [dlt data quality docs](https://dlthub.com/docs/hub/features/quality/data-quality)

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): carry-over from `setup-data-quality`. If missing, ask the user.
- `table` (optional): narrow scope to a single table. If omitted, cover all tables.

## Session context — carry-over from setup-data-quality

This skill is usually entered with context already in session:
- Confirmed pipeline name
- Table list (names + column counts)
- Auto-detected check candidates per table (from `display_schema` hints)

If this context is missing (skill invoked directly), run steps 2–3 of `setup-data-quality` inline: call `display_schema` for each table to recover the schema hints before continuing.

## Steps

### 1. Determine profile and output form

Two questions control how checks are generated.

**Question 1 — profile:**

| Answer | Profile |
|---|---|
| "I want checks to run every time the pipeline loads" | **A** — checks go into the pipeline code |
| "Data is already loaded; I want to check it without re-running the pipeline" | **B** — checks run once against the destination via `dq.run_checks` |

If arriving from `setup-data-quality` with an existing destination and no intent to modify the pipeline, default to Profile B. If ambiguous, ask.

**Question 2 — resource type (Profile A only):**

| Resource type | API form |
|---|---|
| Custom `@dlt.resource` function | Decorator: `@dq.with_checks(...)` above `@dlt.resource` |
| Built-in source (`rest_api`, `sql_database`, `filesystem`) | Dynamic: `dq.with_checks(resource_obj, ...)` after instantiation |

If the user is unsure, check the pipeline file for `@dlt.resource` decorators or `rest_api()` / `sql_database()` calls. Make the call yourself — do not leave it as an open question.

Profile B skips Question 2 entirely — no pipeline file is modified.

### 2. Elicit business intent

**If context is clear** (user just described requirements, or schema hints already suggest obvious checks from `setup-data-quality`) — use those as a starting point and present them for confirmation. Do not re-ask what the user already told you.

**If intent is vague** ("add quality checks", "make sure the data is good") — start from the schema candidates surfaced in `setup-data-quality` and propose sensible defaults. Present them and ask if the user wants to add more:

```
Based on the schema, here are the checks I'd suggest as a starting point:

  orders:
    → is_unique("id")              [id is marked primary_key in schema]
    → is_not_null("customer_id")   [customer_id is non-nullable]

  customers:
    → is_unique("id")              [id is marked primary_key in schema]
    → is_not_null("email")

Anything to add or change? Common additions:
  - Value constraints: "status must be one of active / inactive"
  - Range checks: "amount must be >= 0"
  - Null tracking: "track null_rate on optional fields over time"
```

Wait for the user to respond before generating code. Accept plain-language answers — you will map them to the API.

### 3. Map intent to checks

Translate each stated requirement to the appropriate built-in check. Always prefer native checks over custom logic.

| User says | Check |
|---|---|
| "X must be unique" | `dq.checks.is_unique("X")` |
| "X must not be null / is required" | `dq.checks.is_not_null("X")` |
| "X is the primary key" | `dq.checks.is_unique("X")` *(see note below)* |
| "X must be one of [a, b, c]" | `dq.checks.is_in("X", ["a", "b", "c"])` |
| "X must be >= 0" / any row-level condition | `dq.checks.case("X >= 0")` |

**`is_primary_key` note:** `dq.checks.is_primary_key()` is not yet fully implemented — the SQL template hardcodes `value` instead of substituting the actual column name (marked `# TODO parameterize` in the source). It raises `LineageFailedException` at runtime. Use `dq.checks.is_unique("col")` as a substitute until the library completes the implementation.
<!-- TODO: remove substitute when dlt-hub/dlthub#397 (is_primary_key parameterization) is resolved -->

**`case()` and NULLs:** `case()` treats NULL as a failing row. For nullable columns, either exclude NULLs in the expression (`case("col IS NULL OR col >= 0")`) or add a separate `is_not_null` check if NULLs are also disallowed.

**Validate `is_in` values before committing.** For any `is_in` check, use the `preview_table` MCP tool to sample the column and confirm the allowed set matches real data:

```
preview_table(pipeline="<name>", table="<table>", columns=["<col>"])
```

If the sampled values don't match the user's stated set, flag it:

```
I sampled "status" in orders — found values: active, inactive, pending, cancelled.
Your stated set was ["active", "inactive"]. Should I include "pending" and "cancelled"?
```

Wait for confirmation before finalising the check.

### 4. Map intent to metrics (Profile A only)

**Profile B skips this step.** `dq.run_checks` does not support metrics — they require `@dq.with_metrics` decorators on the resource and run during the pipeline load.

For Profile A: select metrics that give ongoing visibility into the data's health over time. Match to what the user said they want to track, or apply these defaults when no preference is stated:

**Always include on every table:**
```python
dq.metrics.table.row_count()
```

**Include per-column based on type and hints:**

| Column characteristic | Metric |
|---|---|
| Optional (nullable) field | `dq.metrics.column.null_count("col")`, `dq.metrics.column.null_rate("col")` |
| Numeric (amount, price, count) | `dq.metrics.column.mean("col")`, `dq.metrics.column.minimum("col")`, `dq.metrics.column.maximum("col")` |
| High-cardinality text (email, id) | `dq.metrics.column.unique_count("col")` |
| Text with length relevance | `dq.metrics.column.average_length("col")` |

**Include dataset-level metrics once per source:**
```python
dq.metrics.dataset.load_row_count()
dq.metrics.dataset.latest_loaded_at()
```

**Constraint:** `dq.metrics.dataset.*` metrics must be applied on a `@dlt.source` function, not on individual `@dlt.resource` functions. If the pipeline only defines `@dlt.resource` without a `@dlt.source` wrapper, skip dataset-level metrics — adding them to a resource will cause a runtime error.

If the user explicitly says "I want to track X over time" — include the matching metric even if it falls outside these defaults.

### 5. Generate code

Produce ready-to-paste code for each table. Use the correct API form determined in step 1.

**Decorator form** (custom `@dlt.resource`):

```python
from dlt.hub import data_quality as dq  # https://dlthub.com/docs/hub/features/quality/data-quality

@dq.with_checks(
    dq.checks.is_unique("id"),
    dq.checks.is_not_null("customer_id"),
    dq.checks.case("amount >= 0"),
)
@dq.with_metrics(
    dq.metrics.table.row_count(),
    dq.metrics.column.null_rate("customer_id"),
    dq.metrics.column.mean("amount"),
    dq.metrics.column.minimum("amount"),
)
@dlt.resource
def orders():
    yield from fetch_orders()
```

**Dynamic form** (built-in sources like `rest_api`, `sql_database`, `filesystem`):

```python
from dlt.hub import data_quality as dq  # https://dlthub.com/docs/hub/features/quality/data-quality

source = rest_api_source(...)  # or sql_database(...), filesystem(...)
orders = source.resources["orders"]

dq.with_checks(
    orders,
    dq.checks.is_unique("id"),
    dq.checks.is_not_null("customer_id"),
    dq.checks.case("amount >= 0"),
)
dq.with_metrics(
    orders,
    dq.metrics.table.row_count(),
    dq.metrics.column.null_rate("customer_id"),
    dq.metrics.column.mean("amount"),
)
```

Generate one block per table. Do not merge unrelated tables into a single decorator call.

**Profile B — checks dict:**

Do not modify any pipeline file. Produce a `checks` dict to pass directly to `dq.run_checks`:

```python
from dlt.hub import data_quality as dq  # https://dlthub.com/docs/hub/features/quality/data-quality

checks = {
    "orders": [
        dq.checks.is_unique("id"),
        dq.checks.is_not_null("customer_id"),
        dq.checks.case("amount >= 0"),
    ],
    "customers": [
        dq.checks.is_unique("id"),
        dq.checks.is_not_null("email"),
    ],
}
```

This dict is passed to `run-data-quality` as session context and written into `tools/dq_run.py` there. No file is written at this stage.

### 6. Confirm with the user

Present the full set of checks and metrics before any code is written to a file:

```
Here is what I'll add to your pipeline:

Table: orders
  Checks:
    ✓ is_unique("id")
    ✓ is_not_null("customer_id")
    ✓ case("amount >= 0")
  Metrics:
    ✓ table.row_count()
    ✓ column.null_rate("customer_id")
    ✓ column.mean("amount"), column.minimum("amount")

Table: customers
  Checks:
    ✓ is_unique("id")
    ✓ is_not_null("email")
    ✓ is_unique("email")
  Metrics:
    ✓ table.row_count()
    ✓ column.null_count("email")

Does this look right? Say "yes" to proceed, or tell me what to change.
```

Wait for explicit confirmation. Apply any corrections, then re-present the changed items only.

### 7. Apply changes

**Profile A — write to pipeline file:**

Write the changes directly into the existing pipeline file. **Never create a new file for this — the checks and metrics must live alongside the resource definitions they annotate.**

**Before writing, scan the pipeline file for any existing `is_primary_key` calls and replace them with `is_unique` on the same column.** Do not leave `is_primary_key` in the file — it will crash at runtime.

- Decorator form: add `@dq.with_checks(...)` and `@dq.with_metrics(...)` immediately above each `@dlt.resource` decorator in the existing pipeline file.
- Dynamic form: add the `dq.with_checks(...)` / `dq.with_metrics(...)` calls in the existing pipeline script, after the source is instantiated and before `pipeline.run(source)`.
- Add `from dlt.hub import data_quality as dq` to the imports at the top of that same file if not already present.

**Also add the data quality execution call after `pipeline.run(source)`:**

```python
# run data quality checks and metrics against just-loaded data
dq_load_info = pipeline.run(dq.data_quality_checks(pipeline.dataset()))
dq_load_info.raise_on_failed_jobs()
```

`@dq.with_checks` only stores hints in the schema metadata — it does not execute checks on its own. The `dq.data_quality_checks(pipeline.dataset())` call reads those hints and writes results to `_dlt_checks`.

If the pipeline file is not accessible (e.g., it lives in a package), show the user the exact diff and ask them to apply it.

**Profile B — no file write:**

Do not modify any file. The checks dict generated in step 5 is passed forward as session context to `run-data-quality`, which will write `tools/dq_run.py`.

## Output and handover

**Profile A** — pass to `run-data-quality`:
- Confirmed pipeline name
- Tables with checks and metrics applied in the pipeline file
- Resource type (decorator vs. dynamic)

**Profile B** — pass to `run-data-quality`:
- Confirmed pipeline name
- The full checks dict (table → list of checks) as a Python literal
- Profile B flag so `run-data-quality` goes directly to the script-writing path

```
Checks defined. Ready to run.
Moving to run-data-quality →
```

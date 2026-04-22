---
name: define-data-quality-checks
argument-hint: "[pipeline-name] [table]"
description: Use after setup-data-quality to translate schema context and business requirements into concrete dlt checks and metrics.
---

# Define data quality checks

Translate business requirements into concrete dlt DQ checks and metrics, then write them into the pipeline code.

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

### 1. Detect resource type

Before generating any code, determine how the pipeline's resources are defined. This controls which API form to use.

Ask the user (or infer from session context / pipeline file):

> Are these resources defined as custom `@dlt.resource` functions in your own code, or do they come from a dlt built-in source like `rest_api`, `sql_database`, or `filesystem`?

| Resource type | API form |
|---|---|
| Custom `@dlt.resource` function | Decorator: `@dq.with_checks(...)` above `@dlt.resource` |
| Built-in source (`rest_api`, `sql_database`, `filesystem`) | Dynamic: `dq.with_checks(resource_obj, ...)` after instantiation |

If the user is unsure, check the pipeline file for `@dlt.resource` decorators or `rest_api()` / `sql_database()` calls. Make the call yourself — do not leave it as an open question.

### 2. Elicit business intent

**If context is clear** (user just described requirements, or schema hints already suggest obvious checks from `setup-data-quality`) — use those as a starting point and present them for confirmation. Do not re-ask what the user already told you.

**If intent is vague** ("add quality checks", "make sure the data is good") — start from the schema candidates surfaced in `setup-data-quality` and propose sensible defaults. Present them and ask if the user wants to add more:

```
Based on the schema, here are the checks I'd suggest as a starting point:

  orders:
    → is_primary_key("id")         [id is marked primary_key in schema]
    → is_not_null("customer_id")   [customer_id is non-nullable]

  customers:
    → is_primary_key("id")
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

### 4. Map intent to metrics

Select metrics that give ongoing visibility into the data's health over time. Match to what the user said they want to track, or apply these defaults when no preference is stated:

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

If the user explicitly says "I want to track X over time" — include the matching metric even if it falls outside these defaults.

### 5. Generate code

Produce ready-to-paste code for each table. Use the correct API form determined in step 1.

**Decorator form** (custom `@dlt.resource`):

```python
from dlt.hub import data_quality as dq  # https://dlthub.com/docs/hub/features/quality/data-quality

@dq.with_checks(
    dq.checks.is_primary_key("id"),
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
    dq.checks.is_primary_key("id"),
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

### 6. Confirm with the user

Present the full set of checks and metrics before any code is written to a file:

```
Here is what I'll add to your pipeline:

Table: orders
  Checks:
    ✓ is_primary_key("id")
    ✓ is_not_null("customer_id")
    ✓ case("amount >= 0")
  Metrics:
    ✓ table.row_count()
    ✓ column.null_rate("customer_id")
    ✓ column.mean("amount"), column.minimum("amount")

Table: customers
  Checks:
    ✓ is_primary_key("id")
    ✓ is_not_null("email")
    ✓ is_unique("email")
  Metrics:
    ✓ table.row_count()
    ✓ column.null_count("email")

Does this look right? Say "yes" to proceed, or tell me what to change.
```

Wait for explicit confirmation. Apply any corrections, then re-present the changed items only.

### 7. Apply to pipeline file

Once confirmed, write the changes directly into the existing pipeline file. **Never create a new file for this — the checks and metrics must live alongside the resource definitions they annotate.**

- Decorator form: add `@dq.with_checks(...)` and `@dq.with_metrics(...)` immediately above each `@dlt.resource` decorator in the existing pipeline file.
- Dynamic form: add the `dq.with_checks(...)` / `dq.with_metrics(...)` calls in the existing pipeline script, after the source is instantiated and before `pipeline.run(source)`.
- Add `from dlt.hub import data_quality as dq` to the imports at the top of that same file if not already present.

If the pipeline file is not accessible (e.g., it lives in a package), show the user the exact diff and ask them to apply it.

## Output and handover

Pass to `run-data-quality`:
- Confirmed pipeline name
- Tables with checks and metrics now applied
- Resource type (decorator vs. dynamic) — affects how run results are read back

```
Checks and metrics defined. Ready to run.
Moving to run-data-quality →
```
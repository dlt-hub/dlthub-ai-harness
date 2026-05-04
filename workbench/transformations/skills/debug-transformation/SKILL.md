---
name: debug-transformation
description: Debug dlt transformation failures. Use when a transformation fails on a different destination than it was developed on, SQL dialect errors occur after deployment, or pipeline recovery is needed after a failed run.
---

# Debug transformation

Diagnose and fix dlt transformation failures. Two main failure classes: **SQL dialect incompatibility** (transformation works on dev destination, fails on production) and **pipeline state errors** (stale packages, schema drift, failed jobs).

## When to use this skill

- Transformation works on DuckDB locally but fails on BigQuery, Snowflake, or Postgres after deployment
- Pipeline fails with SQL syntax errors or "unsupported function" messages
- You want to verify SQL portability **before** deploying (proactive check)
- Pipeline is stuck in a failed/retry loop
- Columns are missing from output after the first run (NULL-only or computed/derived columns)
- You want to inspect what the transformation actually produced after a successful run

## 1. SQL dialect compatibility

Write dialect-checking scripts to `diagnostics/check_dialect.py` (create `diagnostics/` at the project root if it doesn't exist). Add `diagnostics/` to `.gitignore` — these are temporary diagnostic aids, not part of the transformation code. Delete them after the issue is resolved.

### 1a. Static SQL compatibility checks

Use SQLGlot directly to parse each transformation's SQL in the dev dialect and transpile it to the target dialect — no pipeline connection required, pure static analysis. This catches common dialect issues before deployment and adds two dlt-specific checks that a bare `sqlglot.transpile()` call can miss.

Collect the SQL strings from your `@dlt.hub.transformation` functions (they are the string literals passed to `dataset()`), add them to a `QUERIES` dict, and run:

```python
# diagnostics/check_dialect.py
import re
import sys
from pathlib import Path

import sqlglot
import tomlkit
from sqlglot import expressions as exp


def dest_type_from_profile(profile: str, dest_name: str = "warehouse") -> str:
    path = Path(f".dlt/{profile}.config.toml")
    if not path.exists():
        return ""
    return (
        tomlkit.loads(path.read_text())
        .get("destination", {})
        .get(dest_name, {})
        .get("destination_type", "")
    )


DLT_TO_SQLGLOT = {
    "motherduck": "duckdb",  # MotherDuck uses DuckDB SQL; no separate SQLGlot dialect
}


def to_sqlglot_dialect(dlt_dest: str) -> str | None:
    mapped = DLT_TO_SQLGLOT.get(dlt_dest, dlt_dest)
    try:
        sqlglot.Dialect.get_or_raise(mapped)
    except Exception:
        return None
    return mapped


QUERIES = {
    "dim_person": "SELECT email, first_name FROM hubspot__contacts",
    "fact_activity": "SELECT id, activity_type FROM hubspot__activities",
    # add one entry per transformation function
}

raw_read = dest_type_from_profile("dev") or "duckdb"
raw_write = dest_type_from_profile("prod") or "bigquery"
READ_DIALECT = to_sqlglot_dialect(raw_read)
WRITE_DIALECT = to_sqlglot_dialect(raw_write)

for label, raw, resolved in [
    ("dev", raw_read, READ_DIALECT),
    ("prod", raw_write, WRITE_DIALECT),
]:
    if resolved is None:
        available = sorted(d.value for d in sqlglot.dialects.Dialects)
        print(f"ERROR: no SQLGlot dialect for dlt destination '{raw}' ({label} profile)")
        print(f"Available SQLGlot dialects: {available}")
        sys.exit(1)

print(f"Dialects: {READ_DIALECT} -> {WRITE_DIALECT}\n")

warnings = 0
errors = 0

for name, sql in QUERIES.items():
    query_warnings = []
    query_errors = []

    try:
        parsed = sqlglot.parse_one(sql, read=READ_DIALECT)
        if not isinstance(parsed, exp.Select):
            query_warnings.append(
                f"top-level is {type(parsed).__name__}, not Select; dlt SqlModel may reject it"
            )
    except Exception as e:
        query_errors.append(f"parse failed for {READ_DIALECT}: {e}")

    for identifier in sorted(set(re.findall(r'"([^"\n]+)"', sql))):
        query_warnings.append(
            f'double-quoted identifier "{identifier}"; verify destination quoting in {WRITE_DIALECT}'
        )

    try:
        sqlglot.transpile(
            sql,
            read=READ_DIALECT,
            write=WRITE_DIALECT,
            error_level=sqlglot.ErrorLevel.WARN,
        )
    except Exception as e:
        query_errors.append(f"transpile {READ_DIALECT}->{WRITE_DIALECT} failed: {e}")

    if not query_warnings and not query_errors:
        print(f"[{name}] OK")
        continue

    print(f"[{name}]")
    for warning in query_warnings:
        print(f"  WARN: {warning}")
    for error in query_errors:
        print(f"  ERROR: {error}")
    warnings += len(query_warnings)
    errors += len(query_errors)

print("\nSUMMARY")
print(f"  warnings: {warnings}")
print(f"  errors: {errors}")
sys.exit(1 if warnings or errors else 0)
```

Run with `uv run python diagnostics/check_dialect.py`. Treat `WARN` as a portability risk to inspect, not a guaranteed failure. Treat `ERROR` as a likely rewrite requirement. This static check catches common SQLGlot and dlt `SqlModel` issues, but it does not replace inspecting `Relation.sql()` when deployment still fails.

If either dlt destination is not covered by SQLGlot, the script stops and prints the available SQLGlot dialects. In that case, inspect dlt's actual `Relation.sql()` output or run a target-destination test pipeline instead. SQLGlot supports 31+ dialects — see https://sqlglot.com/sqlglot.html for dialect names.

### 1c. Common dialect-specific patterns to fix

Rewrite these to ANSI SQL so SQLGlot can transpile them to any destination:

| Dialect-specific pattern | Portable ANSI alternative |
|---|---|
| `x::TEXT`, `x::INT` (cast shorthand) | `CAST(x AS VARCHAR)`, `CAST(x AS INTEGER)` |
| `IFNULL(a, b)` | `COALESCE(a, b)` |
| `ILIKE` | `LOWER(x) LIKE LOWER(y)` |
| `INT64` / `STRING` / `FLOAT64` as type names | `BIGINT` / `VARCHAR` / `DOUBLE` |
| `EPOCH_MS()`, `STRFTIME()`, `LIST_AGG()`, etc. | No ANSI equivalent — use `query_dialect` (see below) |
| `QUALIFY` clause | Wrap in subquery with `WHERE` on the window result |

### 1d. When dialect-specific SQL is unavoidable

If a transformation genuinely requires a dialect-specific function with no ANSI equivalent, declare the source dialect with `query_dialect` so SQLGlot knows how to transpile:

```python
@dlt.hub.transformation
def my_transform(dataset: dlt.Dataset):
    yield dataset(
        "SELECT STRFTIME(created_at, '%Y-%m') AS month FROM events",
        query_dialect="duckdb",  # tells dlt this SQL is DuckDB dialect
    )
```

If SQLGlot raises `UnsupportedError` or logs warnings at `unsupported_level`, the construct has no mapping to the target dialect and must be rewritten to an ANSI equivalent or handled in application code.

References:
- SQLGlot supported dialects: https://sqlglot.com/sqlglot.html
- SQLGlot unsupported errors: https://sqlglot.com/sqlglot.html#unsupported-errors
- dlt `Relation` source: https://github.com/dlt-hub/dlt/blob/3583acd7785d3120fa29329d11cfbf379e0258a3/dlt/dataset/relation.py#L276

## 2. Pipeline failure recovery

Use this escalation order. Do not skip steps.

### Step 1: Inspect failures

```bash
dlt pipeline <pipeline_name> failed-jobs
dlt pipeline <pipeline_name> trace
```

Read the error messages before taking any recovery action. Most failures are fixable without touching destination state.

### Step 2: Clear stale packages

If a prior run failed mid-load and left pending packages that keep retrying old (broken) SQL:

```bash
dlt pipeline <pipeline_name> drop-pending-packages
```

Re-run after clearing. If the underlying SQL was fixed, this is often all that is needed.

### Step 3: Reconcile local state

If local pipeline state has drifted from the destination (e.g. after a partial load or schema change):

```bash
dlt pipeline <pipeline_name> sync
```

If no recoverable destination state exists, `sync` may not resolve partial retries — use `drop-pending-packages` first.

### Step 4: Selective drop (last resort)

Only if the steps above do not resolve the failure and incorrect schema or tables were already loaded to the destination:

```bash
dlt pipeline <pipeline_name> drop <resource>   # drop a specific resource
dlt pipeline <pipeline_name> drop --drop-all   # only with explicit user confirmation
```

**Safety rules before dropping:**
- Prefer dropping specific resources over `--drop-all`
- Confirm pipeline name, destination, dataset, and which resources will be dropped before executing
- `drop` removes destination tables and resets matching local state — this forces a full reload and may remove good data alongside bad
- If uncertain which resources are safe to drop, stop and ask the user before executing
- After drop: re-run transformations and validate schema/tables before further loads

References:
- dlt CLI reference: https://dlthub.com/docs/reference/command-line-interface
- `dlt pipeline drop`: https://dlthub.com/docs/reference/command-line-interface#dlt-pipeline-drop

## 3. Missing columns and schema issues

dlt silently drops columns it cannot type-infer — no error, no warning. Two root causes:

### 3a. NULL-only columns

When a column is NULL-only on the first run and no `columns=` hint was provided, dlt strips the column from the schema. Subsequent runs write data but the column is absent.

### 3b. Computed / derived columns

When a transformation uses derived expressions — `md5()`, `strftime()`, `TRY_CAST`, `CASE WHEN ... END`, aggregates with aliases, or function chains — dlt cannot infer the output type from the SQL alone. Without a `columns=` hint the column is silently dropped.

**Diagnose:** compare expected vs actual columns using the MCP `get_table_schema` tool, or inspect via:

```bash
dlt pipeline <pipeline_name> show
```

Identify which computed columns are absent from the output schema. Each missing column needs an explicit `columns=` hint.

**Fix:** add `columns=` hints for every affected column:

```python
@dlt.hub.transformation(
    write_disposition="replace",
    columns={
        "company_sk":   {"data_type": "text",      "nullable": False},
        "joined_at":    {"data_type": "timestamp",  "nullable": True},
        "email_hash":   {"data_type": "text",       "nullable": True},   # md5() result
        "month_bucket": {"data_type": "text",       "nullable": True},   # strftime() result
        "event_count":  {"data_type": "bigint",     "nullable": True},   # COUNT() alias
    },
)
def dim_company(dataset: dlt.Dataset):
    ...
```

`data_type` values must match the key type contract established during `create-transformation` (consistently `text` or `bigint` for surrogate keys).

Apply `columns=` hints for:
- Any column from a `LEFT JOIN` (lookup may return NULL)
- Any cast from string to typed value where the source may be empty
- Any column that was NULL-only in a prior run
- **Any computed or derived column**: `md5()`, `strftime()`, `TRY_CAST`, `CASE WHEN`, aggregate aliases, function chains

### Known DuckDB failure: "Parser Error: Adding columns with constraints not yet supported"

This error surfaces when re-running a transformation with new or modified `columns=` hints against DuckDB — DuckDB's `ALTER TABLE` cannot add constrained columns. The workaround is to drop the dataset and re-run from scratch:

```bash
# DuckDB only — this drops all tables in the dataset
duckdb <path_to_db_file> "DROP SCHEMA <dataset_name> CASCADE;"
```

Then re-run the transformation script. This is DuckDB-specific behavior and will not occur on cloud destinations (BigQuery, Snowflake, Postgres).

Reference: https://dlthub.com/docs/hub/features/transformations

## 4. Validate transformation output

After a successful run, verify the transformation produced the expected result before treating it as done. Use the MCP tools:

- `list_tables` — confirm all CDM tables are present in the target dataset
- `get_row_counts` — verify counts are non-zero and plausible relative to source
- `get_table_schema` — confirm column names and types match the CDM spec
- `preview_table` — inspect a sample of rows for unexpected NULLs, wrong grain, or type mismatches

**What to check:**
- All expected CDM tables exist (no silent skip due to empty resource)
- Row counts are non-zero and plausible relative to source table sizes
- Surrogate key columns are populated (not all NULL)
- Foreign keys in fact tables resolve to values present in dimension tables
- No unexpected duplicate rows (grain violation)
- Computed columns (`md5`, date buckets, etc.) are present and non-NULL where expected
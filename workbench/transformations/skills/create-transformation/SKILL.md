---
name: create-transformation
description: Write dlt transformation functions that map source tables to CDM entities. Use after generate-cdm to produce the transformation Python script.
argument-hint: "[pipeline-name]"
---

# Create transformation

Write `@dlt.hub.transformation` functions that map annotated source tables to CDM entities using ibis.

**Requires:**
- `.schema/annotated-sources.dbml` — source table schemas with concept annotations
- `.schema/taxonomy.json` — confirmed table→concept mappings and natural keys
- `.schema/CDM.dbml` — target CDM schema

If any are missing, run the preceding skills first.

Parse `$ARGUMENTS`:
- `pipeline-name`: the dlt pipeline to transform from (e.g. `hubspot_crm_pipeline`)
- If omitted, check `taxonomy.json` for contributing pipelines and ask user which to target

## Steps

### 1. Read inputs

Read in parallel:
- `.schema/annotated-sources.dbml` — source columns and their concept mappings
- `.schema/taxonomy.json` — table mappings and natural keys
- `.schema/CDM.dbml` — CDM entity definitions and column specs

### 2. Get actual source schema via ibis

**Always use ibis (not `get_table_schema` MCP tool) for actual column types.**
The MCP tool includes untyped/null-only columns that were never materialized in the destination — ibis reflects only what actually exists.

```python
import dlt
import ibis

pipeline = dlt.attach(pipeline_name="<pipeline_name>")
dataset = pipeline.dataset()
relation = dataset.<table_name>
schema = relation.schema()  # authoritative column list
```

Cross-check the annotated columns in `annotated-sources.dbml` against the ibis schema. Note any discrepancies.

### 3. Plan transformation order

**Always run dimensions before facts** — facts join on dimension surrogate keys.

Build an execution order:
1. All conformed dimensions (shared across multiple facts)
2. Non-conformed dimensions
3. Fact tables (after all their dimension FKs exist)

### 4. Write transformation functions

One `@dlt.hub.transformation` function per CDM entity. Wrap all in a `@dlt.source`.

**Use ibis for transformation logic — never pandas DataFrames.**
ibis expressions are lazy, push computation to the source database, and compose cleanly across unions, joins, and window functions. Falling back to `.to_pandas()` for merges defeats this — keep everything in ibis until dlt loads the result.

**Alternatively, pure SQL is supported** — pass a SQL string directly to `dataset()` instead of using ibis expressions (https://dlthub.com/docs/hub/features/transformations#31-alternatively-use-pure-sql-for-the-transformation). SQL can produce more predictable output schemas and may be preferable for simpler transformations or when the user is more comfortable with SQL:

```python
@dlt.hub.transformation
def dim_person(dataset: dlt.Dataset):
    yield dataset("SELECT email, first_name, last_name FROM hubspot__contacts ORDER BY email")
```

Use `query_dialect` if your SQL dialect differs from the destination.

**ibis requires a SQL-capable destination** (BigQuery, Snowflake, DuckDB with file-based access, etc.). If the user requests DuckDB as destination, check whether ibis can connect to it in the context — if not, switch to BigQuery or another cloud destination and inform the user.

**Decorator (default pattern):**
```python
@dlt.hub.transformation(
    write_disposition="replace",
)
def dim_person(dataset: dlt.Dataset):
    ...
```

**Cross-source transformations only** (data from multiple pipelines): ibis connections must be created **before** the CDM pipeline starts. Use module-level connection variables initialised in a setup function called before `pipeline.run()`:

```python
_AC = None
_LUMA = None

def _init_connections() -> None:
    global _AC, _LUMA
    _AC = dlt.pipeline("active_campaigns", destination="bigquery", dataset_name="active_campaigns").dataset().ibis()
    _LUMA = dlt.pipeline("luma_events_data", destination="bigquery", dataset_name="luma_events_data").dataset().ibis()

def dim_person():
    contacts = _AC.table("contacts")
    guests   = _LUMA.table("event_guests")
    ...  # pure ibis — no .to_pandas()

if __name__ == "__main__":
    _init_connections()          # BEFORE pipeline is created
    pipeline = dlt.pipeline(...)
    pipeline.run(my_source())
```

**ibis patterns:**

Surrogate keys — use `.hash().cast("string")` (no `ibis.md5()`):
```python
person_sk = contacts.email.hash().cast("string").name("person_sk")
```

CASE WHEN — use `ibis.cases(...)` not `ibis.case()` (ibis 10+):
```python
ibis.cases((condition, value), else_=default)
```

First-row-per-group (dedup) — use `row_number()` over a window:
```python
import ibis.expr.types as ir
row_num = ibis.row_number().over(ibis.window(group_by=["email"], order_by=[ibis.desc("updated_at")]))
contacts.mutate(rn=row_num).filter(ibis._.rn == 0)
```

Join column references — always reference via original table variable after join (silent ambiguity otherwise):
```python
joined = contacts.join(companies, contacts.company_id == companies.id)
# WRONG: joined.email  ← ambiguous if both tables have email
# RIGHT: contacts.email  ← explicit
```

Cross-source union (from `taxonomy[concept].natural_key` + `taxonomy[concept].tables`):
```python
persons = hubspot_contacts.select(...).union(luma_guests.select(...))
```

**`columns=` hint — REQUIRED for any column that may be NULL on first run:**
```python
@dlt.hub.transformation(
    write_disposition="replace",
    columns={"company_sk": {"data_type": "text", "nullable": True}},
)
def dim_person(dataset: dlt.Dataset):
    ...
```

When to add `columns=`:
- Any column from a LEFT JOIN (lookup may return NULL)
- Any cast from string to typed value where source may be empty
- Any column that was NULL-only in a prior run

Omitting `columns=` causes **silent data loss** — dlt strips the column from the outer SELECT if its schema entry has no `data_type`.

**Do NOT use `mcp__dlt__execute_sql_query` for cloud destinations** — use dlt + ibis directly.

### 5. Write the script

Output file: `transformations/<dataset_name>_to_cdm.py`

Structure:
```python
import dlt
import ibis

@dlt.source
def <dataset_name>_to_cdm():
    # dimensions first
    yield dim_person
    yield dim_company
    yield dim_event
    # facts after
    yield fact_event_attendance

@dlt.hub.transformation(write_disposition="replace")
def dim_person(dataset: dlt.Dataset):
    ...

# ... remaining functions

if __name__ == "__main__":
    pipeline = dlt.pipeline(
        pipeline_name="<business_domain>_pipeline",   # e.g. person_interactions_pipeline
        destination="<destination>",
        dataset_name="<business_domain>",             # no _pipeline suffix on dataset
    )
    load_info = pipeline.run(<business_domain>_to_cdm())
    print(load_info)
```

**Naming convention:** `pipeline_name` and `dataset_name` should reflect the **business domain and central fact**, not the source systems. Derive the name from:
1. The central fact table in `.schema/CDM.dbml` (e.g. `fact_interaction` → `interactions`)
2. The primary dimension in `.schema/ontology.ison` (e.g. `Person`)
3. The use cases in `.schema/taxonomy.json`

Name the dataset after the grain of the star schema — what the data mart *is about*: `person_interactions`, `order_fulfillment`, `event_attendance`. Never use source system names (`hubspot_stripe_cdm`) or generic names (`combined_cdm`, `my_pipeline`). A good name tells an analyst what business process lives in the dataset without reading the code.

### 6. Get feedback before running

Show a summary of:
- Output tables being created
- Source tables used per output table
- Any columns added with explicit type hints and why
- Any source columns skipped and why

Ask user to confirm before running the transformation.

## Output

- `transformations/<dataset_name>_to_cdm.py` — dlt transformation script

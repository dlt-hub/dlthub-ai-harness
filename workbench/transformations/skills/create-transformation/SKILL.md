---
name: create-transformation
description: Create dlt transformations that map source data to a Canonical Data Model (CDM). Use when the user wants to transform raw data into standardized CDM entities, map source tables to canonical structures, or build data transformations based on their ontology and CDM.
argument-hint: "[pipeline-name] [-- [entity-or-hints]]"
---

# Create transformation to canonical model

**Transforms raw source data into a Canonical Data Model (CDM) using dlt transformations.** The ontology defines your business semantics; the CDM formalizes those semantics into implementation-ready entities; transformations map messy source data into that clean structure using `@dlt.hub.transformation`.

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline containing source data. If omitted, infer from session context or ask the user.
- `entity-or-hints` (optional, after `--`): specific entity to transform (e.g., `-- Company`) or hints about transformation goals.

## Prerequisites

### 1. Check for CDM

Read `.schema/CDM.dbml` to understand the target canonical model structure.

If the file doesn't exist:
> No CDM found. The CDM defines your canonical entities and how source data maps to them.
>
> Run `generate-cdm` first to create the canonical data model from your ontology.

**STOP and wait for CDM to be created.**

### 2. Extract source schema

Ask the user for the `pipeline-name` if not already provided as an argument.

#### Path A — dlt-managed pipeline (preferred)

Call `mcp__dlt__list_pipelines` and check if the pipeline name appears in the result.

If found:
1. Call `mcp__dlt__get_pipeline_local_state` to retrieve `destination` and `dataset_name`. Store both — needed for all subsequent data queries.
2. Use dlt + ibis to get the **actual destination columns** (not MCP local state — it includes null-only columns that were never materialized):

```python
import dlt
pipeline = dlt.pipeline(pipeline_name="<name>", destination="<destination>", dataset_name="<dataset_name>")
db = pipeline.dataset().ibis()
for table in sorted(db.list_tables()):
    print(table, db.table(table).schema())
```

3. Build the ISON from the ibis schema results and write `.schema/<pipeline_name>.ison`.

> **STOP — do not begin mapping until `.schema/<pipeline_name>.ison` has been written and you have read it back.**
>
> MCP `get_table_schema` reflects dlt's local normalizer state and may include columns with no `data_type` (seen as null-only, never materialized in the destination). Only ibis reflects what columns actually exist. Mapping against MCP-only metadata will cause `AttributeError` at runtime.

To query sample data at any point, use dlt + ibis directly (not `mcp__dlt__execute_sql_query`, which fails for cloud destinations):

```python
import dlt
pipeline = dlt.pipeline(pipeline_name="<name>", destination="<destination>", dataset_name="<dataset_name>")
db = pipeline.dataset().ibis()
print(db.table("<table>").limit(5).execute())
```

#### Path B — non-dlt source (fallback)

If the pipeline is not found via dlt MCP, ask the user:
- **destination**: e.g. `duckdb`, `postgres`, `bigquery`, `snowflake`
- **dataset_name**: the database/schema name where data lives

Store both values in memory for the remainder of the session.

**Requirements** (must be installed in the environment):
```
dlt[<destination>]  # e.g. dlt[bigquery], dlt[postgres]
ibis-framework
```

**Before executing any code:**
1. Check for a Python environment in the repo (look for `.venv/`, `venv/`, or check if `uv` is available)
2. If using uv: run with `uv run python <script>`
3. If using venv: activate it first (`.venv/Scripts/activate` on Windows, `source .venv/bin/activate` on Unix), then run `python <script>`
4. If no environment found: ask the user how to run Python in their setup
5. If the script takes too long to run (>30 seconds), ask the user to execute it themselves in terminal

Create `extract_schema.py` with the user's connection details:

```python
import dlt

def schema_to_ison(db) -> str:
    """Convert ibis schema to ISON format (https://ison.dev)."""
    lines = []

    # Schema table block
    lines.append("table.schema")
    lines.append("table_name column_name column_type nullable")

    for table_name in sorted(db.list_tables()):
        schema = db.table(table_name).schema()
        for col_name, col_type in schema.items():
            type_str = str(col_type)
            nullable = "true" if "nullable" in type_str.lower() or not type_str.startswith("!") else "false"
            clean_type = type_str.lstrip("!")
            lines.append(f"{table_name} {col_name} {clean_type} {nullable}")

    lines.append("")

    # Parent-child relationships (dlt convention: __ separator)
    lines.append("table.relationships")
    lines.append("child_table parent_table relationship")

    tables = set(db.list_tables())
    for table_name in sorted(tables):
        if "__" in table_name:
            parts = table_name.split("__")
            for i in range(len(parts) - 1, 0, -1):
                potential_parent = "__".join(parts[:i])
                if potential_parent in tables:
                    lines.append(f"{table_name} :{potential_parent} :CHILD_OF")
                    break

    return "\n".join(lines)


if __name__ == "__main__":
    import os

    dataset_name = "<dataset_name>"  # REPLACE: database/schema name

    pipeline = dlt.pipeline(
        pipeline_name="source_data",
        destination="<destination>",  # REPLACE: e.g. "bigquery", "postgres"
        dataset_name=dataset_name
    )
    dataset = pipeline.dataset()
    db = dataset.ibis()

    ison_output = schema_to_ison(db)
    print(ison_output)

    os.makedirs(".schema", exist_ok=True)
    output_path = f".schema/{dataset_name}.ison"
    with open(output_path, "w") as f:
        f.write(ison_output)
    print(f"\nSaved to {output_path}")
```

Run the script from within THE ACTIVE ENVIRONMENT OF THIS REPO:
```bash
python extract_schema.py
```
Then read `.schema/<dataset_name>.ison` to confirm success.

#### ISON output format

Both paths produce `.schema/<name>.ison` in this format:

```
table.schema
table_name column_name column_type nullable
contacts id bigint false
contacts email varchar true
contacts__associations__companies__results id bigint false

table.relationships
child_table parent_table relationship
contacts__associations__companies__results :contacts :CHILD_OF
```

The output contains:
- All tables and their columns with types
- Parent-child relationships based on dlt's `__` naming convention

**Essential Reading:**
- **dlt Transformations**: `https://dlthub.com/docs/hub/features/transformations`
- Dataset access: `https://dlthub.com/docs/general-usage/dataset-access/dataset`
- **Ibis expression reference**: `https://ibis-project.org/reference/` — use this to verify correct ibis API for column operations, casting, joins, and aggregations
- ISON format: `https://ison.dev/spec.html`

## Steps

### 1. Analyze source-to-CDM mapping

Compare the source schema (`.schema/<dataset>.ison`) against the CDM (`.schema/CDM.dbml`):

For each CDM entity, identify:
- Which source table(s) map to it
- Column mappings (source column → CDM attribute)
- Type conversions needed (e.g., `string` → `float` for amounts)
- Joins required (for denormalized CDM entities from multiple source tables)

Create a mapping table:

| CDM Entity | CDM Attribute | Source Table | Source Column | Transform |
|------------|---------------|--------------|---------------|-----------|
| Customer | customer_id | contacts | id | direct |
| Customer | email | contacts | properties__email | direct |
| Customer | name | contacts | properties__firstname, properties__lastname | concat |
| Deal | amount | deals | properties__amount | cast to float |

### 2. Identify mapping discrepancies

Look for gaps and ambiguities:

**Source columns without CDM mapping:**
- Columns in source that don't map to any CDM attribute
- Ask: "Should `properties__slack_user_name` be added to the CDM, or ignored?"

**CDM attributes without source mapping:**
- CDM attributes with no corresponding source column
- Ask: "The CDM expects `customer_status` but the source has no status field. Should we derive it from another field, use a default, or mark as UNKNOWN?"

**Cardinality mismatches:**
- CDM expects one-to-one but source has one-to-many
- Ask: "A contact can have multiple companies via `contacts__associations__companies__results`. Should we pick the primary company, or create multiple Customer records?"

**Type conflicts:**
- Source type incompatible with CDM type
- Ask: "Source `properties__amount` is string but CDM expects float. Should we cast it, or handle parse errors?"

**If a source table has no CDM counterpart**, include it in the discrepancies list — do not extend the CDM unilaterally. CDM design is handled by `generate-cdm`.

**Present all discrepancies to the user and STOP.** Resolve each before generating transformations.

### 3. Generate dlt transformation script

After resolving discrepancies, create `transformations/<dataset>_to_cdm.py`.

**Structure guidelines:**

1. **One transformation function per CDM entity** — Each CDM entity from `.schema/CDM.dbml` gets its own `@dlt.hub.transformation` decorated function

2. **Transformation function signature:**
   - Takes `dataset: dlt.Dataset` as input
   - Yields an ibis expression or SQL relation
   - Use `write_disposition="merge"` for entities with primary keys
   - Set `primary_key` to the CDM entity's canonical identifier

3. **Building the select expression:**
   - Read source table: `dataset.table("<source_table>").to_ibis()`
   - Map each CDM attribute to its source column(s) using the mapping table from Step 1
   - Apply transforms (casting, concatenation, coalesce) as identified

4. **Fact vs dimension table handling** — check `table_type` in `.schema/CDM.dbml`:

   **Dimension tables** (`table_type = dimension`):
   - Generate a surrogate key: prefer a stable source id (`t.id`); if no natural id exists, derive one via `key_expr.cast("string").hash().cast("string")` — see surrogate key patterns in Step 4a
   - Set `primary_key` to the surrogate key column name (from `surrogate_key` in CDM)
   - Set `write_disposition="merge"` on the surrogate key
   - For **SCD Type 2** dimensions (`scd_type = 2`): add `valid_from`, `valid_to`, `is_current` columns. Set `valid_from=ibis.now()`, `valid_to=ibis.null().cast("timestamp")`, `is_current=True` on insert; close previous rows by setting `valid_to` and `is_current=False` on change
   - For **SCD Type 1** (`scd_type = 1`): just overwrite — merge on surrogate key is sufficient

   **Fact tables** (`table_type = fact`):
   - Respect the grain defined in CDM — one row must represent exactly what the grain says
   - Look up dimension surrogate keys by joining on natural keys: `dim.join(fact, dim.natural_key == fact.fk_column).select(..., dim.surrogate_key)`
   - Degenerate dimensions (transaction IDs with no dimension table) stay as plain columns in the fact
   - Do **not** set a surrogate key on fact tables; use the natural transaction identifier or a composite key

5. **Handling relationships (many-to-many):**
   - CDM relationship tables need joins between association tables and parent tables
   - Use `_dlt_parent_id` → `_dlt_id` join pattern for dlt nested tables

6. **Grouping transformations:**
   - Wrap all entity transformations in a `@dlt.source` function
   - This allows running all transformations together

7. **Main execution block:**
   - Create source pipeline pointing to raw data location
   - Create CDM pipeline pointing to CDM dataset location
   - Run dimensions first, then facts (facts depend on dimension surrogate keys)
   - Run: `cdm_pipeline.run(cdm_transformations(source_pipeline.dataset()))`

### 4. Transformation patterns

Apply these patterns based on the mapping table:

| Scenario | Pattern |
|----------|---------|
| Direct mapping | `cdm_attr=table.source_column` |
| Concatenation | `full_name=table.first + " " + table.last` |
| Type casting | `amount=table.amount_str.cast("float64")` |
| Null → sentinel | `status=ibis.coalesce(table.status, "UNKNOWN")` |
| dlt parent-child join | Join on `child._dlt_parent_id == parent._dlt_id` |
| SQL alternative | `yield dataset("SELECT ... FROM ...")` instead of ibis |
| Surrogate key — stable natural key | `customer_sk=table.id` (preferred when source id is stable) |
| Surrogate key — derived hash | `address_sk=key_expr.hash().cast("string")` (no `ibis.md5` — it doesn't exist) |
| Dimension SK lookup in fact | join dim on natural key, select `dim.surrogate_key` (see join rules below) |
| Degenerate dimension | Keep `order_id` as plain column in fact — no dimension table needed |
| SCD Type 2 insert cols | `valid_from=ibis.now(), valid_to=ibis.null().cast("timestamp"), is_current=ibis.literal(True)` |
| Role-playing dimension | Reference the same dimension table twice with aliased joins (e.g., `order_date_sk`, `ship_date_sk` both from `Date` dim) |

### 4a. ibis quick reference

This section replaces the need to look up the ibis docs for the patterns that appear in almost every transformation.

#### Decorator

```python
# CORRECT
@dlt.hub.transformation(write_disposition="merge", primary_key="customer_sk")
def dim_customer(dataset: dlt.Dataset):
    ...

# WRONG — dlt.transformation does not exist
@dlt.transformation(...)
```

#### Column hints — ALWAYS declare nullable/cross-source columns

**`VALIDATED`**: dlt wraps your transformation SQL in an outer `SELECT` generated from its stored schema. Any column that has ever been NULL-only in a prior run has **no `data_type`** in the schema and is silently stripped from the outer SELECT — even if your SQL returns real values for it. This affects:

- Columns from LEFT JOIN lookups (e.g. resolving a surrogate key from another dataset)
- Any column that may be empty on the first run and populated later

**Always declare these columns explicitly in the decorator:**

```python
@dlt.hub.transformation(
    write_disposition="merge",
    primary_key="guest_id",
    columns={
        "contact_sk": {"data_type": "text", "nullable": True},   # LEFT JOIN lookup — may be NULL first run
        "amount":     {"data_type": "double", "nullable": True},  # cast from string — may be empty
    },
)
def fact_event_attendee(dataset: dlt.Dataset):
    return dataset("SELECT ..., c.contact_sk FROM ... LEFT JOIN other_dataset.dim_contact c ...")
```

Omitting `columns=` for these cases causes silent data loss with no error — only a dlt warning: *"The following columns did not receive any data during this load"*.

#### Reading tables

```python
t = dataset.table("contacts").to_ibis()   # ibis expression — use for complex transforms
dataset("SELECT id, email FROM contacts") # SQL string — simpler fallback
```

#### Selecting and renaming columns

```python
t.select(
    customer_sk=t.id,                     # rename
    email=t.properties__email,            # direct
    name=t.first_name + " " + t.last_name # expression
)
```

#### Type casting

```python
t.col.cast("float64")     # string → float
t.col.cast("int64")       # string → integer
t.col.cast("date")        # timestamp → date
t.col.cast("timestamp")   # string → timestamp
t.col.cast("string")      # anything → string (needed before .hash())
```

#### Null handling

```python
ibis.coalesce(t.col, "UNKNOWN")           # first non-null wins; any number of args
ibis.coalesce(t.phone, t.mobilephone)     # fallback chain
ibis.null().cast("timestamp")             # typed null literal
t.col.isnull()                            # boolean: is null?
t.col.notnull()                           # boolean: is not null?
```

#### Boolean filters

```python
t.filter(t.archived.isnull() | ~t.archived)  # exclude archived rows
t.filter(t.status.notnull() & (t.amount > 0))
# & = AND,  | = OR,  ~ = NOT  (all work on ibis boolean columns)
```

#### isin

```python
t.filter(t.type.isin(["contact_to_company", "contact_to_company_unlabeled"]))
# isin accepts a plain Python list
```

#### Constants / literals

```python
ibis.now()                   # current timestamp
True / False                 # bare Python booleans work fine inside .select() — validated
ibis.literal(True)           # explicit form, also works
ibis.null().cast("string")   # null of a specific type — validated
```

#### CASE WHEN

```python
# ibis 10+ API: ibis.cases() takes (condition, result) tuples + else_ kwarg
# ibis.case() does NOT exist; ibis.cases() does NOT support method chaining in ibis 12+
ibis.cases(
    (t.type == "contact_to_company", "WORKS_AT"),
    (t.type == "former_employer_to_employee", "FORMERLY_WORKED_AT"),
    else_="UNKNOWN",
)

# Boolean case
ibis.cases(
    (t.type.isin(["contact_to_company", "contact_to_company_unlabeled"]), ibis.literal(True)),
    else_=ibis.literal(False),
)
```

#### String operations

```python
t.col.strip()                                    # trim whitespace
t.col.lower()                                    # lowercase
t.col.contains("foo")                            # substring check → boolean
(ibis.coalesce(t.first, "") + " " + ibis.coalesce(t.last, "")).strip()  # safe concat
```

#### Surrogate keys

```python
# Preferred: use stable source id directly
customer_sk = t.id

# When no natural id exists (e.g. address derived from fields):
key_expr = ibis.coalesce(t.street, "") + "|" + ibis.coalesce(t.city, "")
address_sk = key_expr.hash().cast("string")
# .hash() returns int64; .cast("string") makes it a usable key
# WARNING: ibis.md5() does NOT exist — do not use it
```

#### First row per group (pick one row per parent)

**`VALIDATED`**: `.first(where=col == col.min())` **does NOT work on BigQuery** — it generates invalid SQL (`IGNORE NULLS` with `min`). Use `row_number()` instead:

```python
# CORRECT — works on BigQuery
w = ibis.window(group_by="_dlt_parent_id", order_by="_dlt_list_idx")
ranked = assoc.mutate(rn=ibis.row_number().over(w))
first_per_group = ranked.filter(ranked.rn == 0).select("_dlt_parent_id", company_id="id")

# SQL fallback (always works)
ds("""
    SELECT _dlt_parent_id, id AS company_id
    FROM (
      SELECT *, ROW_NUMBER() OVER (PARTITION BY _dlt_parent_id ORDER BY _dlt_list_idx) AS rn
      FROM <dataset>.<table>
    ) WHERE rn = 1
""")

# WRONG — fails on BigQuery with 'IGNORE NULLS not allowed for min'
t.group_by("_dlt_parent_id").aggregate(
    company_id=t.id.first(where=t._dlt_list_idx == t._dlt_list_idx.min())
)
```

#### Joins — critical rules

```python
# Basic join
result = left.join(right, left.id == right.foreign_id, how="left")

# CRITICAL — validated: join column ambiguity is SILENT and causes wrong data.
# When two joined tables share a column name (e.g. both have 'id'),
# selecting by name picks the LEFT table silently — no error raised.
# Always reference columns via the original table variable after a join.
result.select(
    customer_sk=left.id,        # ← explicit: left table's id
    company_sk=right.company_sk,  # ← explicit: right table's column
)
# NOT: result.select("id")  ← silently returns left.id even if you wanted right.id

# dlt parent-child join pattern (nested tables use _dlt_parent_id → _dlt_id)
child.join(parent, child._dlt_parent_id == parent._dlt_id)

# Lookup join: resolve a surrogate key from a dimension
lookup = dim.select(natural_id=dim.natural_key, sk=dim.surrogate_key)
fact.join(lookup, fact.fk == lookup.natural_id, how="left").select(..., lookup.sk)
```

#### Union

```python
ibis.union(table_a, table_b, distinct=True)   # UNION DISTINCT
ibis.union(table_a, table_b, distinct=False)  # UNION ALL
# Both tables must have identical column names and compatible types
```

Refer to [dlt transformations docs](https://dlthub.com/docs/hub/features/transformations) for full syntax and [ibis reference](https://ibis-project.org/reference/) for edge cases.

### 5. Validate and test

After generating the script:

1. **Dry run** — Check computed schema before execution:
```python
relation = source_pipeline.dataset().table("contacts").to_ibis().select(...)
print(relation.columns)
```

2. **Run transformations** — Execute in the user's environment
3. **Verify row counts** — `cdm_pipeline.dataset().row_counts().df()`
4. **Spot check data** — Query source or CDM data using dlt + ibis directly:

```python
import dlt
pipeline = dlt.pipeline(pipeline_name="<name>", destination="<destination>", dataset_name="<dataset_name>")
db = pipeline.dataset().ibis()
print(db.table("companies").limit(5).execute())
print(db.sql("SELECT DISTINCT type FROM contacts__associations__companies__results").execute())
```

Run via `uv run python -c "..."`. **Do not use `mcp__dlt__execute_sql_query`** — it fails for cloud destinations (BigQuery, Snowflake, etc.) because the MCP server has no access to destination credentials. `mcp__dlt__list_tables` and `mcp__dlt__get_table_schema` still work fine as they read local pipeline state only.

## Output

```
Transformation script created: transformations/<dataset>_to_cdm.py

Mappings:
- CDM Customer ← contacts (<X> columns mapped)
- CDM Company ← companies (<Y> columns mapped)
- CDM Deal ← deals (<Z> columns mapped)
- CDM CustomerCompany ← contacts__associations__companies__results

Resolved discrepancies:
- <question>: <answer>
...

Next steps:
- Review transformations/<dataset>_to_cdm.py
- Run: python transformations/<dataset>_to_cdm.py
- Verify CDM tables in destination
```
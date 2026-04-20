---
name: create-transformation
description: Write dlt transformation functions that map source tables to CDM entities. Use after generate-cdm to produce the transformation Python script.
argument-hint: "[pipeline-name]"
---

# Create transformation

Write `@dlt.hub.transformation` functions that map annotated source tables to CDM entities, using SQL-first with optional ibis.

**Requires:**
- `.schema/<cdm-name>/taxonomy.json` — confirmed table→concept mappings and natural keys; read `_name` from this file to determine `<cdm-name>`
- `.schema/<cdm-name>/<pipeline_name>.dbml` — annotated source schemas
- `.schema/<cdm-name>/CDM.dbml` — target CDM schema

If any are missing, run the preceding skills first.

The `_name` value from `taxonomy.json` is also the `dataset_name` for the transformation pipeline — do not re-derive it.

Parse `$ARGUMENTS`:
- `pipeline-name`: the dlt pipeline to transform from (e.g. `hubspot_crm_pipeline`)
- If omitted, check `taxonomy.json` for contributing pipelines and ask user which to target

## Steps

### 1. Install dependencies

**Determine destination** — if the destination is not already known from prior context (prior conversation), ask the user which destination they are using before proceeding.

Install the matching ibis backend:

| Destination    | Command                              |
|----------------|--------------------------------------|
| DuckDB         | `uv add "ibis-framework[duckdb]"`    |
| PostgreSQL     | `uv add "ibis-framework[postgres]"`  |
| Snowflake      | `uv add "ibis-framework[snowflake]"` |
| BigQuery       | `uv add "ibis-framework[bigquery]"`  |
| *Some backend* | `uv add ibis-framework[<backend>]`     |

Then install dlt[hub]:

```
uv add "dlt[hub]"
```

Ask the user if they have their dlthub license. If they do not, ask them to obtain one using:

```
dlt license issue dlthub.transformations
```

### 2. Read inputs

Read in parallel:
- `.schema/annotated-sources.dbml` — source columns and their concept mappings
- `.schema/taxonomy.json` — table mappings and natural keys
- `.schema/CDM.dbml` — CDM entity definitions and column specs

### 3. Get actual source schema

Prefer relation schema from dlt dataset objects (not `get_table_schema` MCP tool) for actual column types.
The MCP tool may include untyped/null-only columns that were never materialized in the destination.

```python
import dlt

pipeline = dlt.attach(pipeline_name="<pipeline_name>")
dataset = pipeline.dataset()
relation = dataset.<table_name>
schema = relation.schema()  # authoritative column list
```

Cross-check the annotated columns in `annotated-sources.dbml` against the schema from `relation.schema()`. Note any discrepancies.

### 4. Plan transformation order

**Always run dimensions before facts** — facts join on dimension surrogate keys.

Build an execution order:
1. All conformed dimensions (shared across multiple facts)
2. Non-conformed dimensions
3. Fact tables (after all their dimension FKs exist)

**Do not self-reference transformation outputs while building facts (default).**
By default, fact SQL must be derived from source-side tables/logic (or explicit stage resources), not from newly produced `dim_*` output tables.
This avoids cyclic/incompatible behavior across runs and destinations.

Allowed exception:
- If the user explicitly requests output-to-output dependencies and the destination semantics are confirmed to support that pattern, document it in the plan before writing SQL.

**Define a key type contract before writing any SQL.**
Pick one key type for this pipeline (`text` or `bigint`) and apply it consistently to:
- all surrogate/foreign key casts in SQL or ibis
- every corresponding `columns=` schema hint

Do not mix key representations (`INT64` vs `STRING`) for related keys across dimensions/facts.
If source systems disagree on key type, normalize to the chosen contract in staging/CTEs first.

### 5. Write transformation functions

One `@dlt.hub.transformation` function per CDM entity. Wrap all in a `@dlt.source`.

**Dataset binding is required when yielding from `@dlt.source`.**
When a transformation resource is returned/yielded from a source, pass the dataset argument explicitly (for example `yield dim_person(source_dataset)`). Not binding datasets can raise `IncompatibleDatasetsException`.

```python
@dlt.source
def hubspot_activity_schema(source_dataset: dlt.Dataset):
    # Correct: dataset is explicitly bound
    yield dim_company(source_dataset)
    yield fact_activity(source_dataset)

@dlt.hub.transformation
def dim_company(dataset: dlt.Dataset):
    yield dataset("SELECT company_id, name FROM hubspot__companies")
```

**Default to SQL transformation logic** — pass a SQL string directly to `dataset()` (https://dlthub.com/docs/hub/features/transformations#31-alternatively-use-pure-sql-for-the-transformation).
Use SQL first because it is easier for users to review, generally more reliable for LLM generation, and dlt can transpile dialect differences when needed.

```python
@dlt.hub.transformation
def dim_person(dataset: dlt.Dataset):
    yield dataset("SELECT email, first_name, last_name FROM hubspot__contacts ORDER BY email")
```

If a relation variable is already available (for example `slack_dataset`), treat it as a callable dataset relation and pass SQL directly:

```python
@dlt.hub.transformation
def dim_users(dataset: dlt.Dataset):
    yield dataset("SELECT user_id, email, created_at FROM users")
```

Use `query_dialect` if your SQL dialect differs from the destination.

**Cross-dataset SQL must use fully qualified source references.**
When writing into `<target_dataset>` from a different source dataset, unqualified table names may resolve against the target dataset and fail with "table not found". For BigQuery, always use ``project.dataset.table`` for source-side refs.

```python
@dlt.hub.transformation
def fact_activity(dataset: dlt.Dataset):
    yield dataset(
        """
        SELECT a.id, a.activity_type, a.created_at
        FROM `my_project.source_dataset_name.activities` AS a
        """
    )
```

**Association key check is mandatory before FK logic.**
For nested association tables, verify join lineage first: association table `_dlt_parent_id` joins to parent row `_dlt_id` (not to parent business keys like `id`).
Do this verification before writing any JOIN used to derive foreign keys.

**ibis remains supported as an option** when SQL becomes too verbose for a specific step (complex programmatic expression building, reusable expression fragments, or existing ibis-heavy codebases). If ibis is chosen, keep everything lazy and never fall back to pandas.

Minimal ibis example (single-table transform), adapted from dlt docs:

```python
@dlt.hub.transformation
def dim_person(dataset: dlt.Dataset):
    contacts = dataset.table("hubspot__contacts").to_ibis()
    yield contacts.select("email", "first_name", "last_name").order_by("email").limit(1000)
```

For more complex ibis patterns (joins, aggregations, unions, `row_number`, window functions, etc.) see the [ibis Table expression API](https://ibis-project.org/reference/expression-tables).

**ibis requires a SQL-capable destination** (BigQuery, Snowflake, DuckDB with file-based access, etc.). If the user requests DuckDB as destination, check whether ibis can connect to it in the context — if not, keep SQL-first transformations or switch to a destination that supports the desired ibis workflow.

**Decorator (default pattern):**
```python
@dlt.hub.transformation(
    write_disposition="replace",
)
def dim_person(dataset: dlt.Dataset):
    ...
```

**Cross-source transformations:** use SQL-first where possible by selecting from available datasets in SQL; use ibis connections only when cross-dataset SQL composition is not practical in the current environment.

If ibis is needed for cross-source composition, initialise connections **before** the CDM pipeline starts — see the [ibis Table expression API](https://ibis-project.org/reference/expression-tables) for join, union, and window function patterns.

**`columns=` hint — REQUIRED for any column that may be NULL on first run:**
```python
@dlt.hub.transformation(
    write_disposition="replace",
    columns={"company_sk": {"data_type": "text", "nullable": True}},
)
def dim_person(dataset: dlt.Dataset):
    ...
```

`columns=` `data_type` values for keys must match the key type contract selected in Step 4.

When to add `columns=`:
- Any column from a LEFT JOIN (lookup may return NULL)
- Any cast from string to typed value where source may be empty
- Any column that was NULL-only in a prior run

Omitting `columns=` causes **silent data loss** — dlt strips the column from the outer SELECT if its schema entry has no `data_type`.

**Do NOT use `execute_sql_query` for cloud destinations** — use dlt transformations with SQL-first (or ibis when explicitly selected).

### 6. Write the script

Output file: `transformations/<dataset_name>_to_cdm.py`

Structure:
```python
import dlt

@dlt.source
def <dataset_name>_to_cdm(dataset: dlt.Dataset):
    # dimensions first
    yield dim_person(dataset)
    yield dim_company(dataset)
    yield dim_event(dataset)
    # facts after
    yield fact_event_attendance(dataset)

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

### 7. Get feedback before running

Show a summary of:
- Output tables being created
- Source tables used per output table
- Any columns added with explicit type hints and why
- Any source columns skipped and why

Ask user to confirm before running the transformation.

### 8. Run and recover safely

Run the script from the project root so `.dlt` state resolves correctly. If needed, enforce root CWD in entrypoint:

```python
from pathlib import Path
import os

os.chdir(Path(__file__).resolve().parents[1])  # run from project root
```

**During development iterations**, use the `debug-pipeline` skill from the **rest-api-pipeline** toolkit — it offers more help with failing pipelines, and particularly sets up `dev_mode=True` for development iterations.

**When `dev_mode` is not suitable (production datasets or shared destinations):**

If stale pending packages exist after a failed run, clear them before re-running:

```
# TODO: remove when dlt issue is resolved — drop-pending-packages is a workaround for stuck packages
dlt pipeline <pipeline_name> drop-pending-packages
```

Use `sync` and `drop-pending-packages` for different failure classes:
- `dlt pipeline <pipeline_name> sync` — recover/refresh local pipeline state from destination state.
- `dlt pipeline <pipeline_name> drop-pending-packages` — remove stale failed/pending load packages that can keep retrying old SQL and mask new fixes.

If no recoverable destination state exists, `sync` may not resolve partial package retries; use `drop-pending-packages` before re-run.

**If incorrect schema/tables were already loaded to destination, treat `drop` as last resort.**
Use this escalation order:
1. Inspect first: `dlt pipeline <pipeline_name> failed-jobs` and `dlt pipeline <pipeline_name> trace`
2. Clear stale retries: `dlt pipeline <pipeline_name> drop-pending-packages`
3. Reconcile local state: `dlt pipeline <pipeline_name> sync`
4. Only then consider selective drop: `dlt pipeline <pipeline_name> drop <resource>` (or `--drop-all` only with explicit user confirmation)

Safety rules for `drop`:
- Prefer dropping specific resources over `--drop-all`
- Confirm pipeline name, destination, dataset, and selected resources before accepting the prompt
- Explain that drop removes destination tables and resets matching state; this can force full reloads and may remove good data with bad data
- If uncertain which resources are safe to drop, stop and ask the user before executing
- After drop, re-run transformations and validate schema/tables before further loads

References:
- CLI docs: https://dlthub.com/docs/reference/command-line-interface
- `dlt pipeline drop`: https://dlthub.com/docs/reference/command-line-interface#dlt-pipeline-drop
- Transformations docs: https://dlthub.com/docs/hub/features/transformations

## Output

- `transformations/<dataset_name>_to_cdm.py` — dlt transformation script

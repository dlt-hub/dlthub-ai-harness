---
name: create-snowflake-dynamic-tables
description: "Use when the CDM of a model should live in Snowflake as dynamic tables that Snowflake refreshes on its own: dynamic tables, TARGET_LAG, incremental refresh, a model that stays fresh without a transformation job, or the CDM changed and the dynamic tables must follow. Translates the CDM, the ontology and the source mappings into CREATE DYNAMIC TABLE statements. Not before the CDM exists, and not for semantic views (create-snowflake-semantic-view)."
argument-hint: "[cdm-name]"
---

# Translate the CDM into Snowflake dynamic tables

A dlt transformation materializes the CDM when its job runs. A **dynamic table** is the same `SELECT`, owned by
Snowflake: Snowflake refreshes it on its own so that it is never older than its **target lag**, and refreshes only the
changed rows when the query allows it. This skill translates what the transformations skills produced into one
dynamic table per CDM entity.

Offer both and let the user choose:

| | dlt transformation | dynamic table |
|---|---|---|
| refreshed by | a job and its trigger, for example the success of the load | Snowflake, to stay within the target lag |
| runs on | any destination, also DuckDB on this machine | Snowflake only |
| changed rows only | incremental transformations, written by hand | incremental refresh, when the query allows it |
| costs | the job run | a warehouse refresh at each lag interval, also when nobody reads the table |

**Reference**: https://docs.snowflake.com/en/sql-reference/sql/create-dynamic-table ·
https://docs.snowflake.com/en/user-guide/dynamic-tables-target-lag ·
https://docs.snowflake.com/en/user-guide/dynamic-tables/supported-queries ·
https://docs.snowflake.com/en/user-guide/dynamic-tables-privileges

**Inputs**, in `.dlthub/ontology/<cdm-name>/`, the same ones `create-transformation` reads:
- `<pipeline_name>.dbml`: the annotated source columns and the concepts they map to, one file per pipeline;
- `taxonomy.json`: the table mappings and the natural keys;
- `CDM.dbml`: the entities, their columns, keys, refs and table notes (`table_type`, `surrogate_key`, `scd_type`,
  `grain`);
- `ontology.md`: the descriptions of the entities and their attributes.

When one of them is missing, run the transformations skills first. The source tables must be loaded into Snowflake.

## 1. Agree on the target

Ask, one question at a time:
- **the schema**: the dataset of the CDM, `_name` in `taxonomy.json`, the same place a dlt transformation would
  write. Check that a dlt transformation does not write the same tables: one owner per table;
- **the target lag**: how fresh the model must be, at least `60 seconds` ("The minimum target lag is 60 seconds");
- **the warehouse** that runs the refreshes.

Check the privileges of the role: `CREATE DYNAMIC TABLE` on the schema, `SELECT` on every source table, `USAGE` on the
database, the schema and the warehouse.

## 2. Translate each entity

Order the entities as `create-transformation` does: conformed dimensions, other dimensions, then facts. For each CDM
table write one statement:

```sql
CREATE OR REPLACE DYNAMIC TABLE ANALYTICS.SALES_MODEL.DIM_CUSTOMER (
  CUSTOMER_SK NUMBER COMMENT 'surrogate key',
  SOURCE_ID VARCHAR COMMENT 'the id in the source system',
  EMAIL VARCHAR COMMENT '<the description of the attribute in ontology.md>'
)
  TARGET_LAG = '15 minutes'
  WAREHOUSE = TRANSFORM_WH
  REFRESH_MODE = INCREMENTAL
  COMMENT = '<the description of the entity in ontology.md>; table_type:dimension; scd_type:1'
AS
SELECT
  HASH('crm', c.id) AS customer_sk,
  c.id::VARCHAR AS source_id,
  c.email
FROM ANALYTICS.CRM_RAW.CUSTOMERS AS c;
```

- **Columns**: the names and types of `CDM.dbml`, with the descriptions of `ontology.md` as comments. The column
  list must match the `SELECT`.
- **Mapping**: each CDM column comes from the source column that `<pipeline_name>.dbml` maps to its concept. Read the
  source tables by their full name, `<database>.<dataset>.<table>`. Leave out the `_dlt_*` columns unless the CDM
  names one.
- **Keys**: keep the key type contract of the model (`text` or `bigint`). A surrogate key is a deterministic hash of
  the source and its natural key from `taxonomy.json`: `HASH(...)` for `bigint`, `MD5(...)` for `text`. A fact
  computes its foreign keys with the same expression from its own source rows, so it does not read the dimension
  tables.
- **SCD type 1**: keep the latest row per natural key,
  `QUALIFY ROW_NUMBER() OVER (PARTITION BY <natural key> ORDER BY _dlt_load_id DESC) = 1`. A source loaded with
  `merge` holds one row per key already. **SCD type 2** comes from the pipeline: load the source with dlt's `scd2`
  merge strategy and select its validity columns.
- **A step between source and entity** (deduplication, nested child tables of dlt): its own dynamic table with
  `TARGET_LAG = DOWNSTREAM`, which refreshes only when the entities that read it need fresh data.
- **Dates from timestamps**: dlt writes in a UTC session, but a dynamic table refreshes in the session time zone of
  its owner. A date from a `TIMESTAMP_LTZ` column then shifts for the rows near midnight: convert first,
  `CAST(CONVERT_TIMEZONE('UTC', started_at) AS DATE)`.
- **From a dlt transformation**: when the mapping comes from a dlt transformation, its SQL is the source of truth.
  Translate it to Snowflake SQL (for example DuckDB's `DATE_DIFF` is `DATEDIFF`, and a filter on `ROW_NUMBER()` in a
  subquery is `QUALIFY`), list the columns instead of `SELECT *` so no `_dlt_*` column gets in, and cast each output
  to the type of the table the transformation writes, for example `NUMBER(19,0)` for `bigint`.

## 3. Keep the refresh incremental

Set `REFRESH_MODE = INCREMENTAL` ("For consistent behavior across Snowflake releases, explicitly set the refresh
mode"). When the query cannot refresh incrementally, the creation fails and names the reason: rewrite the query, or
use `FULL` and tell the user that each refresh reprocesses all rows. Not supported for incremental refresh:
- subqueries outside `FROM`, for example `WHERE EXISTS`;
- `MINUS`, `EXCEPT`, `INTERSECT`, and `LIMIT`;
- outer joins on anything but equality;
- `LATERAL` joins other than `LATERAL FLATTEN`;
- `ANY_VALUE`, and `RANK`, `DENSE_RANK` or `PERCENT_RANK` over sliding frames.

A dynamic table refreshes the changes of its source tables. A source that dlt loads with `replace` changes completely
at each load, so each refresh after it reprocesses everything. `append` and `merge` loads change only the new rows.
A small reference table loaded with `replace` and joined into every fact row (a price list, for example) changes
every joined row too: suggest loading it with `merge` on its key.

## 4. Write, show and create

Write all statements, in order, to `.dlthub/ontology/<cdm-name>/snowflake_dynamic_tables.sql`, next to the model.
It is the source of truth. **STOP**: show the user the tables, the target lag, the warehouse and the refresh mode,
and say that the refreshes spend credits for as long as the tables exist. Create them only after an explicit yes.

Run the file with the SQL tool of Cortex Code, or with the Snowflake CLI on the connection of the destination (ask
for its name): `snow sql -c <connection> -f .dlthub/ontology/<cdm-name>/snowflake_dynamic_tables.sql`. The default
`INITIALIZE = ON_CREATE` refreshes each table at creation and fails the creation when the refresh fails, so an error
shows at once.

## 5. Validate

- `SHOW DYNAMIC TABLES IN SCHEMA <schema>;`: `refresh_mode` and `refresh_mode_reason` show what Snowflake chose, and
  `scheduling_state` shows `RUNNING`.
- Compare row counts and a few keys with the source tables. When a dlt transformation writes the same entity, compare
  the schemas (`INFORMATION_SCHEMA.COLUMNS`: name, position, type, precision, scale) and then every row in both
  directions, leaving out dlt's load column:
  `SELECT * EXCLUDE (_DLT_LOAD_ID) FROM <dlt table> MINUS SELECT * FROM <dynamic table>`, and the reverse. Matching
  schemas and counts can still hide different values. Every difference must be explained or fixed.
- `SELECT * FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(NAME => '<schema>.<table>'));` shows the
  refreshes and their duration.

Tuning the lag and the warehouse, and why a refresh is slow or full, needs the Snowflake internals: in Cortex Code use
its bundled skills, elsewhere hand the task over (`delegate-to-cortex-code`).

## 6. Keep in sync

When the CDM, the mappings or the ontology change, compare the file with the model, show every change, and after a
yes run the changed statements again. `CREATE OR REPLACE` rebuilds the table and refreshes it from scratch.
`ALTER DYNAMIC TABLE <name> SET TARGET_LAG = '<duration>'` changes the lag in place, and `SUSPEND` stops the refreshes.

## Output

- `.dlthub/ontology/<cdm-name>/snowflake_dynamic_tables.sql`: the statements, the source of truth. Commit it.
- The dynamic tables in Snowflake, validated against the sources.

## Next

A semantic view on the dynamic tables (`create-snowflake-semantic-view`), so Cortex Analyst and agents answer
questions on the model.

---
name: validate-transformation
description: Validate the output of a dlt transformation against the CDM. Use when the user wants to check if a transformation produced correct results, verify row counts, detect join fan-out, find unexpected NULLs in required fields, or confirm the CDM dataset looks right after running a transformation.
argument-hint: "[transformation-name-or-pipeline] [concerns]"
---

# Validate transformation output

After running a `@dlt.hub.transformation`, verify the CDM output is correct: schema matches expectations, row counts are sane, joins didn't fan out, required fields are populated, and no silent data loss occurred.

Parse `$ARGUMENTS`:
- `transformation-name-or-pipeline` (optional): the CDM pipeline name or transformation script path. If omitted, infer from session context or ask.
- `concerns` (optional, after `--`): specific things to check (e.g. `-- NULLs in contact_sk`, `-- row count mismatch`)

## 1. Connect to the CDM pipeline

Use dlt + ibis to connect to the transformation output dataset:

```python
import dlt

cdm_pipeline = dlt.pipeline(
    pipeline_name="<cdm_pipeline_name>",
    destination="<destination>",
    dataset_name="<cdm_dataset_name>"
)
db = cdm_pipeline.dataset().ibis()
print(db.list_tables())
```

Run via `uv run python -c "..."`. **Do not use `mcp__dlt__execute_sql_query`** — it fails for cloud destinations (BigQuery, Snowflake, etc.) because the MCP server has no access to destination credentials.

## 2. Check row counts

Compare row counts between the source pipeline and the CDM output. Fan-out (CDM has far more rows than source) usually means a join multiplied rows.

```python
import dlt

# CDM counts
cdm_pipeline = dlt.pipeline(pipeline_name="<cdm_pipeline_name>", destination="<destination>", dataset_name="<cdm_dataset_name>")
cdm_db = cdm_pipeline.dataset().ibis()
for t in sorted(cdm_db.list_tables()):
    print(t, cdm_db.table(t).count().execute())

# Source counts (for comparison)
src_pipeline = dlt.pipeline(pipeline_name="<source_pipeline_name>", destination="<destination>", dataset_name="<source_dataset_name>")
src_db = src_pipeline.dataset().ibis()
for t in sorted(src_db.list_tables()):
    print(t, src_db.table(t).count().execute())
```

**Red flags:**
- CDM entity has 0 rows → transformation didn't produce output; check decorator and `columns=` hints
- CDM entity has far more rows than source → join fan-out (missing dedup or wrong join key)
- CDM entity has far fewer rows than source → unexpected filter or failed join dropped rows

## 3. Check for silent data loss (columns= hints)

dlt wraps transformation SQL in an outer `SELECT` generated from its stored schema. Any column that was NULL-only in a prior run has **no `data_type`** in the schema and is silently stripped — even if your SQL returns real values now.

Check for this by inspecting the CDM schema via ibis and comparing against the CDM definition:

```python
import dlt

cdm_pipeline = dlt.pipeline(pipeline_name="<cdm_pipeline_name>", destination="<destination>", dataset_name="<cdm_dataset_name>")
db = cdm_pipeline.dataset().ibis()

for table in sorted(db.list_tables()):
    schema = db.table(table).schema()
    print(f"\n{table}:")
    for col, dtype in schema.items():
        print(f"  {col}: {dtype}")
```

Compare this against `.schema/CDM.dbml`. Any CDM attribute missing from the ibis schema output was silently dropped. Fix by adding a `columns=` hint in the `@dlt.hub.transformation` decorator:

```python
@dlt.hub.transformation(
    write_disposition="merge",
    primary_key="contact_sk",
    columns={
        "company_sk": {"data_type": "text", "nullable": True},   # LEFT JOIN lookup
        "amount":     {"data_type": "double", "nullable": True},  # may be NULL first run
    },
)
```

See [dlt transformations docs](https://dlthub.com/docs/hub/features/transformations) for full `columns=` reference.

## 4. Check required fields for NULLs

For each CDM entity, check that required (non-nullable) fields are populated:

```python
import dlt

cdm_pipeline = dlt.pipeline(pipeline_name="<cdm_pipeline_name>", destination="<destination>", dataset_name="<cdm_dataset_name>")
db = cdm_pipeline.dataset().ibis()

t = db.table("dim_contact")
null_counts = {
    col: t.filter(t[col].isnull()).count().execute()
    for col in t.columns
}
print({k: v for k, v in null_counts.items() if v > 0})
```

**What to do with NULLs:**
- NULL in a surrogate key → source join failed; check join key names and that the source table is populated
- NULL in a business field that shouldn't be NULL → add `ibis.coalesce(t.col, "UNKNOWN")` in the transformation
- NULL in an optional lookup (LEFT JOIN to another dataset) → expected; declare `columns={"col": {"data_type": "text", "nullable": True}}`

## 5. Check primary key uniqueness

Duplicate primary keys corrupt merge behavior — later rows silently overwrite earlier ones. Verify uniqueness for each entity with a `primary_key`:

```python
import dlt

cdm_pipeline = dlt.pipeline(pipeline_name="<cdm_pipeline_name>", destination="<destination>", dataset_name="<cdm_dataset_name>")
db = cdm_pipeline.dataset().ibis()

t = db.table("dim_contact")
pk = "contact_sk"   # replace with actual primary key
total = t.count().execute()
distinct = t.select(pk).distinct().count().execute()
print(f"total={total}, distinct={distinct}, duplicates={total - distinct}")
```

Duplicates usually come from:
- Join fan-out before dedup (add a `row_number()` window or `DISTINCT` on the PK)
- Multiple source rows mapping to the same surrogate key (check hash key expression)

## 6. Spot-check sample rows

Pull sample rows and visually confirm mappings look correct:

```python
import dlt

cdm_pipeline = dlt.pipeline(pipeline_name="<cdm_pipeline_name>", destination="<destination>", dataset_name="<cdm_dataset_name>")
db = cdm_pipeline.dataset().ibis()
print(db.table("dim_contact").limit(10).execute().to_string())
```

For cross-dataset lookups, verify the lookup resolved correctly by checking a known record end-to-end:

```python
db.sql("""
    SELECT f.guest_id, f.contact_sk, c.email
    FROM fact_event_attendee f
    LEFT JOIN cdm_dataset.dim_contact c ON c.contact_sk = f.contact_sk
    LIMIT 10
""").execute()
```

## 7. Review with user and iterate

Present findings to the user:

```
CDM validation summary
──────────────────────
dim_contact:    1,234 rows  ✓ no NULLs in required fields  ✓ PK unique
dim_company:      456 rows  ✓
fact_event:     9,876 rows  ⚠ contact_sk NULL on 234 rows (LEFT JOIN miss)
                            ⚠ Missing columns= hint — amount was stripped
```

For each issue, identify the fix (see `create-transformation` skill for patterns) and re-run the transformation:

```bash
uv run python transformations/<dataset>_to_cdm.py
```

Then re-validate until the user is satisfied.

## Next steps

- **Validation passes** → hand off to `data-exploration` toolkit to build reports and notebooks on the CDM
- **Transformation needs fixing** → edit `transformations/<dataset>_to_cdm.py` and re-run; consult `create-transformation` for ibis patterns and `columns=` hints
- **CDM structure needs changing** → go back to `generate-cdm` to update `.schema/CDM.dbml`, then regenerate the transformation
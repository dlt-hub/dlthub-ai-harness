---
name: annotate-sources
description: Annotate dlt pipeline sources for transformation. Use when the user wants to transform data, do data modelling, design a data model, describes their data sources and use cases, or wants to build a CDM from existing pipelines.
argument-hint: "[sources] [use-cases]"
---

# Annotate sources

Map the user's data sources to canonical business concepts, ready for ontology and CDM design.

Parse `$ARGUMENTS`:
- `source names`: comma-separated pipeline or source names (e.g. "hubspot, luma, stripe")
- `use cases`: what the user wants to do with the data (e.g. "track event attendance, link contacts to companies")

If not provided in arguments, ask the user for:
1. Which data sources / dlt pipelines they have
2. What they want to achieve (use cases, analytics goals, reports)
3. How the sources relate to each other (important)

**IMPORTANT: Confirm the exact pipeline name (or dataset name + destination) for every source before doing anything else.** Do not proceed to any extraction step until all names are known. Wrong pipeline names will cause all subsequent MCP calls to fail silently or with confusing errors.

All `.schema/` files are written under `<project_root>/.schema/<cdm-name>/`. The CDM folder name is derived from the user's use cases and confirmed in step 2 below.

## Steps

### 1. Check dlt pipelines exist

Use `list_pipelines` MCP tool to list all local dlt pipelines.

For each source the user mentioned, one of three cases applies:

**Case A — local pipeline found** → note the pipeline name, dataset name, and destination. Schema will be read from `~/.dlt/pipelines/<pipeline_name>/schemas/<pipeline_name>.schema.json` in step 3.

Before proceeding, check whether any tables in the schema JSON already have `x-taxonomy` blocks. If they do, this pipeline was annotated in a previous session. Prompt the user:

```
This pipeline already has taxonomy annotations from a previous session.

If the schema has changed since then (new tables, new columns, updated endpoints), run check-taxonomy first to see what's drifted before re-annotating.

Would you like to:
  1) Run check-taxonomy first (recommended)
  2) Continue with annotate-sources
```

Wait for the user's choice before proceeding.

**Case B — no local pipeline, but data already exists on a remote destination** → ask the user for:
- The exact dataset name on the destination (e.g. `luma_events_data`)
- The destination type (e.g. `bigquery`, `snowflake`)

Schema will be extracted via a dlt ibis script in step 3. Note: `x-taxonomy` annotations cannot be embedded in the schema JSON for Case B sources — no local pipeline state exists. Mappings for Case B tables will be recorded in `taxonomy.md` only.

**Case C — no pipeline and no remote dataset** → stop and hand over to **rest-api-pipeline** toolkit:

```
Pipeline for "<source>" not found locally or remotely.
You need to ingest it first — use the rest-api-pipeline toolkit to build a dlt pipeline for it.
```

Only continue when **all stated sources are confirmed as Case A or Case B**.

### 2. Confirm CDM folder name

Derive a folder name from the user's stated use cases using the same grain-based naming convention as `dataset_name` in `create-transformation` — what the data mart *is about* (e.g. `person_interactions`, `order_fulfillment`, `event_attendance`). Never use source system names or generic names.

Propose the name and confirm with the user:

```
I'll store all schema files under .schema/person_interactions/

Does this name work, or would you like to change it?
```

Wait for confirmation. This name will also be used as the `dataset_name` when the transformation script is written — so it's worth getting right now.

### 3. Read source schemas

**For Case A (local pipeline):** Read the dlt schema JSON directly:

```
~/.dlt/pipelines/<pipeline_name>/schemas/<pipeline_name>.schema.json
```

On Windows this resolves to `C:\Users\<username>\.dlt\pipelines\...`. In any Python scripts, construct the path as:
```python
from pathlib import Path
schema_path = Path.home() / ".dlt" / "pipelines" / "<pipeline_name>" / "schemas" / f"<pipeline_name>.schema.json"
```

Load the JSON and read the `tables` object into context. Skip all `_dlt_*` tables — these are dlt internals and are never mapped to concepts. The `tables` object is the working artifact for all subsequent steps.

**For Case B (remote dataset, no local pipeline):** Write and run a Python script using dlt ibis to extract the schema. Write the script to `tools/get_<source>_schema.py`:

```python
"""Get <source> schema from <destination> via dlt ibis."""
import json
import dlt

pipeline = dlt.pipeline(
    pipeline_name="<pipeline_name>",
    destination="<destination>",
    dataset_name="<dataset_name>",
)

dataset = pipeline.dataset()
ibis_conn = dataset.ibis()
tables = ibis_conn.list_tables()

schema_tables = {}
for table_name in tables:
    if table_name.startswith("_dlt"):
        continue
    t = ibis_conn.table(table_name)
    schema_tables[table_name] = {
        "columns": {name: {"data_type": str(dtype)} for name, dtype in zip(t.schema().names, t.schema().types)}
    }

print(json.dumps(schema_tables, indent=2))
```

Run with `uv run python tools/get_<source>_schema.py`. Capture the output into context as the working schema for this source.

### 4. Identify core business entities

Read the use cases the user stated. Using the source schemas loaded in step 3 and stated use cases only:

**SCOPE CONSTRAINT — no inference beyond source data:** Entity names, descriptions, and use-case coverage must be grounded strictly in (a) columns that actually exist in the source schemas and (b) use cases the user explicitly stated. Do **not** add, suggest, or imply attributes, metrics, or business concepts that have no corresponding column in the source data. For example: if the source has a `contacts` table but no `roi`, `lead_score`, or `is_icp` columns, do not mention or include those concepts anywhere.

1. Propose the core **business entities** the use cases revolve around.
   - Collapse synonyms: `guest` → `Person`, `contact` → `Person`, `attendee` → `Person`
   - Use neutral, domain-agnostic names (PascalCase nouns): `Person`, `Company`, `Event`, `Order`
   - Explain each entity and why it covers the stated use cases — based only on columns present in the source schema

2. Present the proposed entities to the user and confirm:

```
Here are the core business entities I see in your data:

  Person — any individual (contact, guest, attendee, lead)
    Covers: track event attendance, link contacts to companies

  Company — an organisation
    Covers: link contacts to companies

Does this look right? You can rename, merge, or add anything.
```

Wait for explicit confirmation before proceeding. Keep all decisions in context — nothing is written to disk until step 7b.

### 5. Filter source tables by relevance

Using the schema loaded in step 3, for each table automatically judge relevance against the confirmed canonical concepts.

**Excluded** = tables with no plausible connection to any concept (e.g. internal audit logs, pipeline metadata, dlt system tables like `_dlt_loads`, `_dlt_pipeline_state`).

Do NOT ask the user — apply your judgement. Record exclusions in context (table name + reason in business language) for step 7b.

### 6. Match source tables to business entities

For each remaining (non-excluded) table, propose which business entity it belongs to.

Present a mapping table to the user:

| Source table | Represents | Confidence | Notes |
|---|---|---|---|
| hubspot__contacts | Person | high | primary contact record |
| luma__guests | Person | high | event attendee |
| hubspot__companies | Company | high | |

- User may correct mappings, reassign tables, or mark a table as excluded
- Wait for explicit confirmation

Record confirmed mappings in context. Nothing written to disk yet.

### 7. Identify cross-source natural keys

Find all concepts whose confirmed tables come from **more than one source pipeline**.

For each such concept:
1. List the contributing tables
2. Propose a **natural key** (the column(s) that can union/link rows across sources)
   - Common candidates: `email`, `external_id`, `phone`, `name` (last resort)
   - Prefer stable, unique, non-nullable fields

Present proposals to the user:

```
Person appears in HubSpot (contacts) and Luma (guests) — we can link them using a shared field.
  Suggested link field: email
  Reason: both sources have email as a unique identifier for the same person

Does this work, or would you prefer a different field?
(Say "keep separate" if these should not be merged across sources.)
```

- User may override the field or keep the two tables separate
- Wait for explicit confirmation

Record confirmed natural keys in context.

### 7b. Write annotations

All decisions are now confirmed. Write two artifacts in a single pass.

**1. Patch `x-taxonomy` into dlt schema JSON (Case A pipelines only)**

Write a Python script for each Case A pipeline at `tools/annotate_<pipeline_name>_schema.py`. Populate `taxonomy` with all confirmed mappings from this session:

```python
"""Patch x-taxonomy annotations into dlt schema JSON for <pipeline_name>."""
import json
from pathlib import Path

schema_path = Path.home() / ".dlt" / "pipelines" / "<pipeline_name>" / "schemas" / "<pipeline_name>.schema.json"
schema = json.loads(schema_path.read_text())

# Confirmed table→concept mappings from annotate-sources session
taxonomy = {
    "hubspot__contacts": {
        "concept": "Person",
        "role": "primary",
        "natural_key": "email",
    },
    "luma__guests": {
        "concept": "Person",
        "role": "secondary",
        "natural_key": "email",
    },
    "hubspot__companies": {
        "concept": "Company",
        "role": "primary",
        "natural_key": None,
    },
}

for table_name, annotation in taxonomy.items():
    if table_name in schema["tables"]:
        schema["tables"][table_name]["x-taxonomy"] = annotation
    else:
        print(f"Warning: table '{table_name}' not found in schema — skipping")

schema_path.write_text(json.dumps(schema, indent=2))
print(f"Patched {len(taxonomy)} tables in {schema_path}")
```

The resulting `x-taxonomy` block sits alongside dlt's own `x-normalizer` at the table level:

```json
"contacts": {
  "name": "contacts",
  "columns": { "..." },
  "write_disposition": "replace",
  "x-normalizer": { "seen-data": true },
  "x-taxonomy": {
    "concept": "Person",
    "role": "primary",
    "natural_key": "email"
  }
}
```

Run with `uv run python tools/annotate_<pipeline_name>_schema.py`. Confirm output before proceeding.

**2. Write `taxonomy.md`**

Write `.schema/<cdm-name>/taxonomy.md`. Use business language throughout — translate excluded table names into business-language categories (e.g. `hubspot__email_events__propertyhistory` → "historical property change logs"). Raw table names appear only in the "Where it comes from" table rows.

```markdown
# Data Model Review: {model_name}

> Generated: {date}  
> Pipeline: `{pipeline_name}`  
> Source: {source_description, e.g. "HubSpot CRM + Luma events"}  
> Status: **Draft — awaiting review**

---

## What this document is

This is a summary of how your data has been organized for analysis. It describes the key business concepts, where they come from, and how they relate to each other.

**If you're reviewing this:** check that the definitions match how your business actually works. Flag anything that looks wrong or missing.

---

## Concepts

### {Concept Name}

**What it is:** {description in business language}

**Used for:** {use cases as a sentence — e.g. "Breaking down revenue by company, rolling up to parent group"}

**Where it comes from:**

| Source | Called there | How it maps |
|--------|-------------|-------------|
| {e.g. HubSpot} | {e.g. Contact} | {e.g. One contact = one person} |
| {e.g. Luma} | {e.g. Guest} | {e.g. Matched by email} |

**Assumptions:**
- {any assumptions made during annotation, or "None"}

---

*Repeat for each concept.*

---

## Not included in this model

> This model focuses on **{scope}**. Data related to {excluded categories in business language — no table names} was excluded because it falls outside this scope. If you need any of these for your analysis, flag it.

---

## What's missing (known gaps)

- {gaps identified during annotation — concepts needed by use cases but absent from source data}
- {or "None identified yet"}

---

## Review

| Concept | Approved | Reviewer | Date | Notes |
|---------|----------|----------|------|-------|
| {Concept} | ☐ | | | |

**Overall model approval:** ☐ Ready for production
```

### 8. Confirm with user

Present a summary of all decisions recorded and files written:

```
Decisions recorded and written:

Concepts:
  Person — contact (HubSpot), guest (Luma) — linked by email
  Company — company (HubSpot)

Excluded:
  hubspot__email_events__propertyhistory — property change log, not a business entity

Written:
  ~/.dlt/pipelines/hubspot_crm_pipeline/schemas/hubspot_crm_pipeline.schema.json — x-taxonomy added to 3 tables
  ~/.dlt/pipelines/luma_pipeline/schemas/luma_pipeline.schema.json — x-taxonomy added to 1 table
  .schema/person_interactions/taxonomy.md — ready for business review

Anything to correct before we move on?
```

If corrections are needed: update `taxonomy` in the annotation script, re-run it, and update `taxonomy.md` to match.

## Output

- `~/.dlt/pipelines/<pipeline_name>/schemas/<pipeline_name>.schema.json` — `x-taxonomy` block added to each mapped table; sits alongside `x-normalizer` (Case A pipelines only)
- `.schema/<cdm-name>/taxonomy.md` — business-facing model review document for sign-off

Hand over to `create-ontology` skill.
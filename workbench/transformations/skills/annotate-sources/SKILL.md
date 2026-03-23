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

All `.schema/` files are written under `<project_root>/.schema/<cdm-name>/`. The CDM folder name is derived from the user's use cases and confirmed in step 3 below.

## Steps

### 1. Check dlt pipelines exist

Use `list_pipelines` MCP tool to list all local dlt pipelines.

For each source the user mentioned, one of three cases applies:

**Case A — local pipeline found** → note the pipeline name, dataset name, and destination. Schema will be extracted via `export_schema` in step 2.

**Case B — no local pipeline, but data already exists on a remote destination** → ask the user for:
- The exact dataset name on the destination (e.g. `luma_events_data`)
- The destination type (e.g. `bigquery`, `snowflake`)

Schema will be extracted via a dlt ibis script in step 2. Do NOT hand off to rest-api-pipeline — the data is already there.

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

### 3. Extract source schemas

**For Case A (local pipeline):** call `export_schema` MCP tool with `output_format: "dbml"` and `save_to_file: "<project_root>/.schema/<cdm-name>/<pipeline_name>.dbml"`.

**For Case B (remote dataset, no local pipeline):** write and run a Python script using dlt ibis to extract the schema and write it as DBML.

Write the script to `tools/get_<source>_schema.py`:

```python
"""Get <source> schema from <destination> via dlt ibis and write as DBML."""
import dlt

pipeline = dlt.pipeline(
    pipeline_name="<pipeline_name>",   # use the dataset name as pipeline name
    destination="<destination>",        # e.g. "bigquery"
    dataset_name="<dataset_name>",      # e.g. "luma_events_data"
)

dataset = pipeline.dataset()
ibis_conn = dataset.ibis()
tables = ibis_conn.list_tables()

lines = []
for table_name in tables:
    if table_name.startswith("_dlt"):
        continue
    t = ibis_conn.table(table_name)
    lines.append(f'Table "{table_name}" {{')
    for name, dtype in zip(t.schema().names, t.schema().types):
        nullable = "" if str(dtype).endswith("!") else ""
        lines.append(f'    "{name}" {dtype}')
    lines.append("}")
    lines.append("")

dbml = "\n".join(lines)
output_path = "<project_root>/.schema/<cdm-name>/<pipeline_name>.dbml"
with open(output_path, "w") as f:
    f.write(dbml)
print(f"Schema written to {output_path}")
print("Tables found:", tables)
```

Run with `uv run python tools/get_<source>_schema.py`. Confirm the file was written before proceeding.

This produces one DBML file per pipeline. These files are the working artifacts for all subsequent steps — they will be annotated in place as mappings and natural keys are confirmed.

### 4. Identify core business entities

Read the use cases the user stated. Using the source schemas and stated use cases only:

**SCOPE CONSTRAINT — no inference beyond source data:** Entity names, descriptions, and use-case coverage must be grounded strictly in (a) columns that actually exist in the source schemas and (b) use cases the user explicitly stated. Do **not** add, suggest, or imply attributes, metrics, or business concepts that have no corresponding column in the source data. For example: if the source has a `contacts` table but no `roi`, `lead_score`, or `is_icp` columns, do not mention or include those concepts anywhere — not in descriptions, not in assumptions, not as "could be added later". Only record what the data actually contains.

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

   - Wait for explicit confirmation before proceeding

3. Write `.schema/<cdm-name>/taxonomy.json` with the confirmed concepts.

**Format:** top-level keys are canonical concept names (PascalCase). Each concept holds its references (source-system synonyms) and all related metadata. Excluded tables, version, and CDM name are stored under reserved `_excluded`, `_version`, and `_name` keys.

```json
{
  "_version": "1.0",
  "_name": "person_interactions",
  "Person": {
    "description": "Any individual — contact, guest, attendee, or lead",
    "use_cases": ["track event attendance", "link contacts to companies"],
    "references": ["guest", "contact", "attendee"],
    "tables": [],
    "natural_key": null,
    "assumptions": ["'guest' and 'contact' collapsed into Person"]
  },
  "Company": {
    "description": "An organisation",
    "use_cases": ["link contacts to companies"],
    "references": ["organization", "account"],
    "tables": [],
    "natural_key": null,
    "assumptions": []
  },
  "_excluded": []
}
```

### 5. Filter source tables by relevance

Read each `.schema/<cdm-name>/<pipeline_name>.dbml`. For each table, automatically judge relevance against the confirmed canonical concepts.

**Excluded** = tables with no plausible connection to any concept (e.g. internal audit logs, pipeline metadata, dlt system tables like `_dlt_loads`, `_dlt_pipeline_state`).

Do NOT ask the user — apply your judgement. Record each exclusion under `_excluded`:

```json
{"table": "hubspot__email_events__propertyhistory", "reason": "property change log, not a business entity"}
```

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

Add confirmed tables under each concept's `tables` array:

```json
"Person": {
  ...
  "tables": [
    {"table": "hubspot__contacts", "source_pipeline": "hubspot_crm_pipeline", "role": "primary"},
    {"table": "luma__guests", "source_pipeline": "luma_pipeline", "role": "secondary"}
  ]
}
```

### 7. Identify cross-source natural keys

Find all concepts whose `tables` array contains entries from **more than one source pipeline**.

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

Set the confirmed natural key on the concept:

```json
"Person": {
  ...
  "natural_key": "email"
}
```

### 7b. Annotate DBML files

After steps 6 and 7 are confirmed, edit each `.schema/<cdm-name>/<pipeline_name>.dbml` to embed semantic annotations as DBML `Note` blocks and inline comments.

**Table-level note** — on every mapped table, add a `Note` with the canonical concept, role, and (if applicable) natural key:

```dbml
Table "contacts" [note: 'concept: Person | role: primary | natural_key: email'] {
    ...
}
```

**Field-level note** — on the natural key column, mark it explicitly:

```dbml
    "email" text [note: 'natural_key']
```

**Excluded tables** — add a note so they are visually distinct:

```dbml
Table "_dlt_loads" [note: 'excluded: dlt internal table'] {
    ...
}
```

This makes the DBML files self-documenting — `create-ontology` can read concept mappings directly from the DBML without cross-referencing `taxonomy.json`.

### 8. Confirm with user

Read `.schema/<cdm-name>/taxonomy.json` and present a summary of all recorded decisions:
- Concepts and their synonym collapses
- Excluded tables and reasons

Ask the user to review before proceeding:

```
Decisions recorded:
1. "guest" and "contact" are both treated as Person
2. hubspot__email_events__propertyhistory skipped — property change log, not a business entity
3. ...

Anything to correct before we move on?
```

Apply any corrections to `taxonomy.json`.

## Output

- `.schema/<cdm-name>/<pipeline_name>.dbml` — one annotated file per pipeline (table/field notes carry concept, role, natural_key, exclusion)
- `.schema/<cdm-name>/taxonomy.json` — concept-keyed: references, table mappings, natural keys, assumptions, exclusions; `_name` holds the confirmed CDM folder name

Hand over to `create-ontology` skill.

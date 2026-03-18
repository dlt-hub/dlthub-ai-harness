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

### 2. Extract source schemas

**For Case A (local pipeline):** call `export_schema` MCP tool with `output_format: "dbml"` and `save_to_file: "<absolute_path>/.schema/<pipeline_name>.dbml"`.

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
output_path = "<absolute_path>/.schema/<pipeline_name>.dbml"
with open(output_path, "w") as f:
    f.write(dbml)
print(f"Schema written to {output_path}")
print("Tables found:", tables)
```

Run with `uv run python tools/get_<source>_schema.py`. Confirm the file was written before proceeding.

This produces one DBML file per pipeline. These files are the working artifacts for all subsequent steps — they will be annotated in place as mappings and natural keys are confirmed.

### 3. Identify core business entities

Read the use cases the user stated. Using your knowledge of the domain and the source schemas:

1. Propose the core **business entities** the use cases revolve around.
   - Collapse synonyms: `guest` → `Person`, `contact` → `Person`, `attendee` → `Person`
   - Use neutral, domain-agnostic names (PascalCase nouns): `Person`, `Company`, `Event`, `Order`
   - Explain each entity and why it covers the stated use cases

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

3. Write `.schema/taxonomy.ison` with the confirmed concepts.

**Format:** top-level keys are canonical concept names (PascalCase). Each concept holds its references (source-system synonyms) and all related metadata. Excluded tables and version are stored under reserved `_excluded` and `_version` keys.

```json
{
  "_version": "1.0",
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

### 4. Filter source tables by relevance

Read each `.schema/<pipeline_name>.dbml`. For each table, automatically judge relevance against the confirmed canonical concepts.

**Excluded** = tables with no plausible connection to any concept (e.g. internal audit logs, pipeline metadata, dlt system tables like `_dlt_loads`, `_dlt_pipeline_state`).

Do NOT ask the user — apply your judgement. Record each exclusion under `_excluded`:

```json
{"table": "hubspot__email_events__propertyhistory", "reason": "property change log, not a business entity"}
```

### 5. Match source tables to business entities

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

### 6. Identify cross-source natural keys

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

### 6b. Annotate DBML files

After steps 5 and 6 are confirmed, edit each `.schema/<pipeline_name>.dbml` to embed semantic annotations as DBML `Note` blocks and inline comments.

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

This makes the DBML files self-documenting — `create-ontology` can read concept mappings directly from the DBML without cross-referencing `taxonomy.ison`.

### 7. Confirm with user

Read `.schema/taxonomy.ison` and present a summary of all recorded decisions:
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

Apply any corrections to `taxonomy.ison`.

## Output

- `.schema/<pipeline_name>.dbml` — one annotated file per pipeline (table/field notes carry concept, role, natural_key, exclusion)
- `.schema/taxonomy.ison` — concept-keyed: references, table mappings, natural keys, assumptions, exclusions

Hand over to `create-ontology` skill.

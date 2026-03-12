---
name: annotate-sources
description: Annotate dlt pipeline sources for transformation. Use when the user wants to transform data, describes their data sources and use cases, or wants to build a CDM from existing pipelines.
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
3. how the sources relate to each other (important)

## Steps

### 1. Check dlt pipelines exist

Use `list_pipelines` MCP tool to list all local dlt pipelines.

For each source the user mentioned:
- **Found** → note the pipeline name, dataset name, and destination
- **Not found** → first ask if it exists, if it does not: stop and hand over to **rest-api-pipeline** toolkit:

```
Pipeline for "<source>" not found locally.
You need to ingest it first — use the rest-api-pipeline toolkit to build a dlt pipeline for it.
```
- If it does exist then ask for dataset name and destination, then connect to it via dlt ibis and get schema, write it as dbml.

Only continue when **all stated sources have a corresponding pipeline or pre-existing dataset**.

### 2. Extract source schemas

For each confirmed pipeline, call `export_schema` with `output_format: "dbml"` and `save_to_file: "<absolute_path>/.schema/<pipeline_name>.dbml"`.

This produces one DBML file per pipeline. These files are the working artifacts for all subsequent steps — they will be annotated in place as mappings and stitch keys are confirmed.

### 3. Derive canonical concepts from use cases

Read the use cases the user stated. Using your knowledge of the domain and the source schemas:

1. Propose a **canonical concept list** — the business entities the use cases revolve around.
   - Collapse synonyms: `guest` → `Person`, `contact` → `Person`, `attendee` → `Person`
   - Use neutral, domain-agnostic names (PascalCase nouns): `Person`, `Company`, `Event`, `Order`
   - Explain each concept and why it covers the stated use cases

2. Present the proposed concepts to the user and confirm:
   - They may rename, merge, or add concepts
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
    "stitch_key": null,
    "assumptions": ["'guest' and 'contact' collapsed into Person"]
  },
  "Company": {
    "description": "An organisation",
    "use_cases": ["link contacts to companies"],
    "references": ["organization", "account"],
    "tables": [],
    "stitch_key": null,
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

### 5. Map relevant tables to canonical concepts

For each remaining (non-excluded) table, propose which canonical concept it maps to.

Present a mapping table to the user:

| Source table | Maps to concept | Confidence | Notes |
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

### 6. Identify cross-source stitching

Find all concepts whose `tables` array contains entries from **more than one source pipeline**.

For each such concept:
1. List the contributing tables
2. Propose a **join key** (the column(s) that can union/link rows across sources)
   - Common candidates: `email`, `external_id`, `phone`, `name` (last resort)
   - Prefer stable, unique, non-nullable fields

Present proposals to the user:

```
Concept: Person
  Sources: hubspot__contacts, luma__guests
  Proposed stitch key: email
  Reason: both tables have email as a unique identifier
```

- User may override the key or mark two tables as non-stitchable (separate sub-concepts)
- Wait for explicit confirmation

Set the confirmed stitch key on the concept:

```json
"Person": {
  ...
  "stitch_key": "email"
}
```

### 6b. Annotate DBML files

After steps 5 and 6 are confirmed, edit each `.schema/<pipeline_name>.dbml` to embed semantic annotations as DBML `Note` blocks and inline comments.

**Table-level note** — on every mapped table, add a `Note` with the canonical concept, role, and (if applicable) stitch key:

```dbml
Table "contacts" [note: 'concept: Person | role: primary | stitch_key: email'] {
    ...
}
```

**Field-level note** — on the stitch key column, mark it explicitly:

```dbml
    "email" text [note: 'stitch_key']
```

**Excluded tables** — add a note so they are visually distinct:

```dbml
Table "_dlt_loads" [note: 'excluded: dlt internal table'] {
    ...
}
```

This makes the DBML files self-documenting — `create-ontology` can read concept mappings directly from the DBML without cross-referencing `taxonomy.ison`.

### 7. Present all assumptions

Collect and display all assumptions recorded in steps 3 and 4:
- Concept definitions and synonym collapses
- Excluded tables and reasons

Ask the user to review and correct anything before proceeding:

```
Assumptions made:
1. "guest" and "contact" both map to Person concept
2. hubspot__email_events__propertyhistory excluded — property change log, not a business entity
3. ...

Anything to correct before we proceed to ontology design?
```

Apply any corrections to `taxonomy.ison`.

## Output

- `.schema/<pipeline_name>.dbml` — one annotated file per pipeline (table/field notes carry concept, role, stitch_key, exclusion)
- `.schema/taxonomy.ison` — concept-keyed: references, table mappings, stitch keys, assumptions, exclusions

Hand over to `create-ontology` skill.

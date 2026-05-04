---
name: create-ontology
description: Build a business entity graph (ontology) from annotated sources and taxonomy. Use after annotate-sources to design the entity model before CDM generation.
---

# Create ontology

Build a formal entity graph from the confirmed source annotations and taxonomy, ready for Kimball CDM design.

**Requires:**
- `~/.dlt/pipelines/<pipeline_name>/schemas/<pipeline_name>.schema.json` — one per source pipeline, with `x-taxonomy` blocks written by `annotate-sources`
- `.schema/<cdm-name>/taxonomy.md` — concept definitions, use cases, and source mappings written by `annotate-sources`

If either is missing, run `annotate-sources` first.

**Discovering pipeline names and CDM folder:** Pipeline names are available from the current session context if `annotate-sources` was just run. If starting cold, read the `Pipeline:` line from `taxonomy.md` to get pipeline name(s). Read `taxonomy.md` to determine the CDM folder name — it appears in the file path itself (`.schema/<cdm-name>/taxonomy.md`).

### Key concept: natural key

A **natural key** is a column whose value is derived from the real-world domain and is therefore consistent across multiple source systems. For example, `email` appearing in both `contacts` (HubSpot) and `event_guests` (Luma) means a single person can be matched and merged across both sources.

When a concept has a natural key, rows from different source tables that share the same natural key value are treated as the **same entity** — they become one row in the CDM, not two. This determines:
- Which source "wins" for each attribute when both have a value (**master source**)
- Whether rows that exist in only one source are still included (**union vs. intersection**)

## Steps

### 1. Build entity list

Run a Python script to read all annotated tables from each pipeline's schema JSON. This script collects every table that has an `x-taxonomy` block and groups them by concept:

```python
"""Read x-taxonomy annotations from dlt schema JSONs."""
import json
from pathlib import Path

pipeline_names = ["<pipeline_name_1>", "<pipeline_name_2>"]  # from session context or taxonomy.md

concepts = {}  # concept → list of {table, pipeline, role, natural_key, columns}

for pipeline_name in pipeline_names:
    schema_path = Path.home() / ".dlt" / "pipelines" / pipeline_name / "schemas" / f"{pipeline_name}.schema.json"
    schema = json.loads(schema_path.read_text())
    for table_name, table in schema.get("tables", {}).items():
        taxonomy = table.get("x-taxonomy")
        if not taxonomy:
            continue
        concept = taxonomy["concept"]
        concepts.setdefault(concept, []).append({
            "table": table_name,
            "pipeline": pipeline_name,
            "role": taxonomy.get("role"),
            "natural_key": taxonomy.get("natural_key"),
            "columns": table.get("columns", {}),
        })

print(json.dumps(concepts, indent=2))
```

Run with `uv run python tools/read_taxonomy.py`. Use the output as the working dataset for all subsequent steps.

Also read `.schema/<cdm-name>/taxonomy.md` to get concept descriptions, use cases, and assumptions (written in business language during `annotate-sources`).

For each top-level concept found: create one ontology entity, name = concept key (PascalCase), mark as `inferred: false`.

### 2. Confirm natural key handling

**Before deriving any attributes**, for every concept that has a `natural_key` in its `x-taxonomy` block (i.e. the same `natural_key` appears on tables from more than one pipeline), explicitly ask the user how they want conflicts resolved. Do not assume a strategy.

Present the concept with its natural key, the contributing sources, and the three options:

```
Person appears in HubSpot (contacts) and Luma (event_guests), linked by email.

When the same person appears in both and their data conflicts, which should we trust?

  A) Prefer whichever source has a value — fall back to the other if blank
     → "Use HubSpot if available, fall back to Luma"
  B) Always use one source, ignore the other entirely
     → "Always use HubSpot, even if a field is blank"
  C) Decide field by field
     → "Use HubSpot for name/phone, Luma for registration date"

Also: what about people who only exist in one source?
  1) Include everyone (recommended)
  2) Only include people present in both sources

Which combination (A/B/C) and (1/2)?
```

Wait for explicit confirmation. Record the chosen strategy in context before proceeding to attribute derivation.

### 3. Derive attributes per entity

**SCOPE CONSTRAINT — no inference beyond source data:** Only include attributes that correspond to actual columns in the source schema. Do **not** add computed fields, business metrics, or domain concepts (e.g. `roi`, `is_icp`, `lead_score`, `lifetime_value`) unless a column with that data already exists in one of the source tables. If a useful attribute is missing from the data, record it as a semantic gap (step 5).

For each concept, use the `columns` collected in step 1 for all tables mapped to that concept.

For each column:
- Include column name, dlt `data_type`, source table, source pipeline
- Apply the confirmed natural key strategy from step 2 to flag the **master source** per attribute
- Skip dlt internal columns: `_dlt_load_id`, `_dlt_id`, `_dlt_root_id`, `_dlt_parent_id`, `_dlt_list_idx`

Where the same logical attribute appears in multiple sources under different names (e.g. `phone` in contacts, `phone_number` in guests):
- Propose a canonical attribute name
- Present conflicts to the user and confirm:

```
Both sources have a phone field for Person, but named differently:
  HubSpot (contacts): phone
  Luma (guests): phone_number

Suggested unified name: phone  |  Primary source: HubSpot (contacts)
OK?
```

Wait for confirmation before proceeding.

### 4. Define relationships

Two sources of relationships:

**From natural keys** (`x-taxonomy.natural_key` in schema JSONs):
- Each natural key defines a union relationship between tables of the same concept
- Record as a `STITCHED_BY` edge with the key column

**From structural FKs** in source schema columns:
- Identify columns that reference another entity by name pattern (e.g. `company_id` → Company entity, `event_id` → Event entity)
- Map to inter-entity relationships
- Use UPPER_SNAKE_CASE edge labels (e.g. `BELONGS_TO`, `ATTENDED`, `PLACED_BY`)

### 5. Flag semantic gaps

Compare entity list against the user's stated use cases (from `taxonomy.md` — read the "Used for:" lines under each concept).

If a use case requires a concept that has **no `x-taxonomy`-annotated table**:
- Flag it as a semantic gap
- Record it: `{"gap": "Contract entity needed for billing use case, no source table found"}`
- Suggest where this data might come from (new pipeline, manual input, derivable from existing tables)

Present gaps to the user before writing output.

### 6. Write ontology

Write `.schema/<cdm-name>/ontology.md` — the developer-facing entity graph summary. One section per entity:

```markdown
# Ontology: {cdm-name}

> Generated: {date}

---

## {Entity Name}

{Short description from taxonomy.md}

**Sources:** {pipeline_name} → {table_name} (primary), {pipeline_name} → {table_name} (secondary)  
**Natural key:** {column, or "none"}  
**Merge strategy:** {strategy confirmed in step 2, or "n/a — single source"}

### Attributes

| Canonical name | Type | Master source | Also in | Notes |
|---|---|---|---|---|
| email | text | hubspot__contacts | luma__guests | natural_key |
| first_name | text | hubspot__contacts | | |

### Relationships

| Relationship | To | Via | Source |
|---|---|---|---|
| BELONGS_TO | Company | hubspot__contacts.associated_company_id | structural FK |
| STITCHED_BY | Person | email | natural key |

---
```

If semantic gaps were found in step 5, append:

```markdown
## Semantic gaps

| Concept | Use case | Note |
|---|---|---|
| Contract | track subscription billing | no source table found |
```

After writing the file, explicitly ask the user to open and review `.schema/<cdm-name>/ontology.md` before continuing:

```
Please review `.schema/<cdm-name>/ontology.md` — it summarises every entity, its attributes, and the relationships between them.

Let me know if anything looks wrong or needs changing before we move on.
```

Wait for explicit confirmation before handing over to `generate-cdm` skill.

## Output

- `.schema/<cdm-name>/ontology.md` — entity graph with attributes, relationships, merge strategies, and gaps

Hand over to `generate-cdm` skill.
---
name: create-ontology
description: Build a business entity graph (ontology) from annotated sources and taxonomy. Use after annotate-sources to design the entity model before CDM generation.
---

# Create ontology

Build a formal entity graph from the confirmed source annotations and taxonomy, ready for Kimball CDM design.

**Requires** `.schema/<cdm-name>/<pipeline_name>.dbml` (one per pipeline, annotated) and `.schema/<cdm-name>/taxonomy.json` from `annotate-sources`.
If either is missing, run `annotate-sources` first.

Read `_name` from `taxonomy.json` to determine `<cdm-name>` — all files in this skill are under that folder.

### Key concept: natural key

A **natural key** is a column whose value is derived from the real-world domain and is therefore consistent across multiple source systems. For example, `email` appearing in both `contacts` (AC) and `event_guests` (Luma) means a single person can be matched and merged across both sources.

When a concept has a natural key, rows from different source tables that share the same natural key value are treated as the **same entity** — they become one row in the CDM, not two. This determines:
- Which source "wins" for each attribute when both have a value (**master source**)
- Whether rows that exist in only one source are still included (**union vs. intersection**)

## Steps

### 1. Build entity list

Read `.schema/taxonomy.json`. For each top-level key that is not prefixed with `_` (i.e. not `_version`, `_excluded`):
- Create one ontology entity per canonical concept
- Name = concept key (PascalCase)
- Mark as `inferred: false` (grounded in confirmed source mappings)

### 2. Confirm natural key handling

**Before deriving any attributes**, for every concept that has a `natural_key` in `taxonomy.json`, explicitly ask the user how they want conflicts resolved. Do not assume a strategy.

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

Wait for explicit confirmation. Record the chosen strategy in the ontology `assumption` field before proceeding to attribute derivation.

### 3. Derive attributes per entity

**SCOPE CONSTRAINT — no inference beyond source data:** Only include attributes that correspond to actual columns in the source schema. Do **not** add computed fields, business metrics, or domain concepts (e.g. `roi`, `is_icp`, `lead_score`, `lifetime_value`) unless a column with that data already exists in one of the source tables. If a useful attribute is missing from the data, record it as a semantic gap (step 5), not as an attribute.

For each entity, collect all columns from **all source tables mapped to that concept** (from `taxonomy[concept].tables`).

For each column:
- Include column name, dlt type, source table, source pipeline
- Apply the confirmed natural key strategy from step 2 to flag the **master source** per attribute

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

**From natural keys** (`taxonomy.json` → `concept.natural_key`):
- Each natural key defines a union relationship between tables of the same concept
- Record as a `STITCHED_BY` edge with the key column

**From structural FKs** in source schemas (`.schema/<cdm-name>/<pipeline_name>.dbml`):
- Identify foreign key columns (e.g. `company_id` on contacts → Company entity)
- Map to inter-entity relationships
- Use UPPER_SNAKE_CASE edge labels (e.g. `BELONGS_TO`, `ATTENDED`, `PLACED_BY`)

### 5. Flag semantic gaps

Compare entity list against the user's stated use cases (from `taxonomy.json` → `concept.use_cases`).

If a use case requires a concept that has **no contributing source table**:
- Flag it as a semantic gap
- Record it as an assumption: `{"gap": "Contract entity needed for billing use case, no source table found"}`
- Suggest where this data might come from (new pipeline, manual input, derivable from existing tables)

Present gaps to the user before writing output.

### 6. Write ontology

Write `.schema/ontology.ison` in Graph ISON format (https://graph.ison.dev/) — tabular DSV sections, NOT JSON:

```ison
nodes.Entity
id       label    inferred  assumption
Person   Person   false     Collapses hubspot contact + luma guest. Natural key: email.
Company  Company  false     Master source: hubspot__companies.

nodes.Attribute
entity           name        type       master_source          also_in          note
:Entity:Person   email       text       hubspot__contacts      luma__guests     natural_key
:Entity:Person   first_name  text       hubspot__contacts

edges.BELONGS_TO
from              to               via                                        inferred
:Entity:Person    :Entity:Company  hubspot__contacts.associated_company_id   false

edges.STITCHED_BY
from            to              via    inferred
:Entity:Person  :Entity:Person  email  false
```

Rules:
- One `nodes.<Type>` section per entity type; one `edges.<LABEL>` section per relationship label
- Node references use `:Type:id` syntax (e.g. `:Entity:Person`)
- Attributes are a separate `nodes.Attribute` section with an `entity` reference column
- Tab-separate columns; use a blank line between sections

If semantic gaps were found in step 5, append:

```ison
nodes.SemanticGap
concept   use_case                       note
Contract  track subscription billing     no source table found
```

## Output

- `.schema/<cdm-name>/ontology.ison` — entity graph with attributes, relationships, and gaps
- `.schema/<cdm-name>/ontology.md` — human-readable summary (required). One section per entity with: a short description, attribute table (name | type | source | notes), relationships table, and a final assumptions & exclusions list.

After writing both files, explicitly ask the user to open and review `.schema/<cdm-name>/ontology.md` before continuing:

```
Please review `.schema/ontology.md` — it summarises every entity, its attributes, and the relationships between them.

Let me know if anything looks wrong or needs changing before we move on.
```

Wait for explicit confirmation before handing over to `generate-cdm` skill.
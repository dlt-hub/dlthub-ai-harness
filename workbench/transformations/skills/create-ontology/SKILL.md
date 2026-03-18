---
name: create-ontology
description: Build a business entity graph (ontology) from annotated sources and taxonomy. Use after annotate-sources to design the entity model before CDM generation.
---

# Create ontology

Build a formal entity graph from the confirmed source annotations and taxonomy, ready for Kimball CDM design.

**Requires** `.schema/<pipeline_name>.dbml` (one per pipeline, annotated) and `.schema/taxonomy.ison` from `annotate-sources`.
If either is missing, run `annotate-sources` first.

### Key concept: natural key

A **natural key** is a column whose value is derived from the real-world domain and is therefore consistent across multiple source systems. For example, `email` appearing in both `contacts` (AC) and `event_guests` (Luma) means a single person can be matched and merged across both sources.

When a concept has a natural key, rows from different source tables that share the same natural key value are treated as the **same entity** — they become one row in the CDM, not two. This determines:
- Which source "wins" for each attribute when both have a value (**master source**)
- Whether rows that exist in only one source are still included (**union vs. intersection**)

## Steps

### 1. Build entity list

Read `.schema/taxonomy.ison`. For each top-level key that is not prefixed with `_` (i.e. not `_version`, `_excluded`):
- Create one ontology entity per canonical concept
- Name = concept key (PascalCase)
- Mark as `inferred: false` (grounded in confirmed source mappings)

### 2. Confirm natural key handling

**Before deriving any attributes**, for every concept that has a `natural_key` in `taxonomy.ison`, explicitly ask the user how they want conflicts resolved. Do not assume a strategy.

Present the concept with its natural key, the contributing sources, and the three options:

```
Concept: Person
Natural key: email
Sources: contacts (AC), event_guests (Luma)

When the same person exists in both sources, how should attribute conflicts be resolved?

  A) COALESCE — prefer non-null values; if both have a value, pick a priority source
     → "Use AC if available, fall back to Luma"
  B) Strict master — always use one source; ignore the other source's values entirely
     → "Always use AC, even if a field is null"
  C) Source-specific — decide per attribute which source wins
     → "Use AC for name/phone, Luma for registration date"

Also: should the entity include people who exist in only one source?
  1) Union (recommended) — include everyone from both sources
  2) Intersection — only include people who appear in both sources

Which option for conflict resolution (A/B/C) and scope (1/2)?
```

Wait for explicit confirmation. Record the chosen strategy in the ontology `assumption` field before proceeding to attribute derivation.

### 3. Derive attributes per entity

For each entity, collect all columns from **all source tables mapped to that concept** (from `taxonomy[concept].tables`).

For each column:
- Include column name, dlt type, source table, source pipeline
- Apply the confirmed natural key strategy from step 2 to flag the **master source** per attribute

Where the same logical attribute appears in multiple sources under different names (e.g. `phone` in contacts, `phone_number` in guests):
- Propose a canonical attribute name
- Present conflicts to the user and confirm:

```
Attribute conflict: phone field for Person
  hubspot__contacts.phone       (master source candidate)
  luma__guests.phone_number

Proposed canonical name: phone  |  Master source: hubspot__contacts
Correct?
```

Wait for confirmation before proceeding.

### 4. Define relationships

Two sources of relationships:

**From natural keys** (`taxonomy.ison` → `concept.natural_key`):
- Each natural key defines a union relationship between tables of the same concept
- Record as a `STITCHED_BY` edge with the key column

**From structural FKs** in source schemas (`.schema/<pipeline_name>.dbml`):
- Identify foreign key columns (e.g. `company_id` on contacts → Company entity)
- Map to inter-entity relationships
- Use UPPER_SNAKE_CASE edge labels (e.g. `BELONGS_TO`, `ATTENDED`, `PLACED_BY`)

### 5. Flag semantic gaps

Compare entity list against the user's stated use cases (from `taxonomy.ison` → `concept.use_cases`).

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

- `.schema/ontology.ison` — entity graph with attributes, relationships, and gaps
- `.schema/ontology.md` — human-readable summary (required). One section per entity with: a short description, attribute table (name | type | source | notes), relationships table, and a final assumptions & exclusions list.

Hand over to `generate-cdm` skill.
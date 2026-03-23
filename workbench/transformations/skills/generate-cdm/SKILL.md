---
name: generate-cdm
description: Generate a Canonical Data Model (CDM) in DBML using Kimball dimensional modeling. Use after create-ontology to produce the implementation-ready CDM schema.
---

# Generate CDM

Translate the ontology into an implementation-ready Canonical Data Model using Kimball dimensional modeling.

**Requires** `.schema/<cdm-name>/ontology.ison` from `create-ontology`.
If missing, run `create-ontology` first.

Read `_name` from `.schema/<cdm-name>/taxonomy.json` to determine `<cdm-name>` — all files in this skill are under that folder.

Reference: DBML format — https://dbml.org/docs/

## Steps

### 1. Classify entities as fact or dimension

Read `.schema/ontology.ison`. For each entity, apply Kimball classification:

| Signals | Classification |
|---|---|
| Describes a business event or transaction (e.g. EventAttendance, Order, PageView) | **Fact table** |
| Describes a stable business object (e.g. Person, Company, Product) | **Reference table** |
| A reference table shared across multiple fact tables | **Shared reference table** |

Present the classification to the user and confirm before proceeding:

```
Here's how I'd structure your data model:

  Reference tables (who/what your data is about):
    dim_person — Person (shared across all facts)
    dim_company — Company (shared across all facts)
    dim_event — Event

  Fact tables (the events/transactions):
    fact_event_attendance — one row per person per event attended

Does this look right?
```

Agree on **shared reference tables** early — they must be consistent across all fact tables.

### 2. Define grain for every fact table

For each fact table, write an explicit grain statement:
> "One row per **[unit]** per **[unit]**"

Example: "One row per person per event attended."

The grain drives:
- Which columns go in the fact table vs. a dimension
- The grain key (column combination used to detect duplicates)
- The surrogate key definition

Never proceed without a confirmed grain.

### 3. Design dimension tables

For each dimension entity:
- Add a **surrogate key** (`<entity_name>_sk`, bigint or string hash)
- Assign **SCD type**:
  - **Type 1** (default): overwrite on change — use for attributes where history doesn't matter
  - **Type 2**: track history — adds `valid_from` (timestamp), `valid_to` (timestamp, nullable), `is_current` (bool)
  - Use Type 2 for: status, tier, segment, role — anything an analyst might want "as of" a date
- Include `source_id` (natural key from source) and `source_pipeline` for lineage
- Null semantics: assign sentinel rows (`UNKNOWN`, `NOT_APPLICABLE`) — **never use NULL as FK** (Kimball Rule #6)

### 4. Design fact tables

For each fact table:
- Reference dimension surrogate keys as FKs (never natural keys in the fact)
- Add a **degenerate dimension** for the natural transaction key if useful (e.g. `event_id`)
- Include additive measures (counts, amounts) and semi-additive measures clearly labelled
- No descriptive attributes — push those to dimensions

### 5. Review entity equivalence

Check for aliases that only become visible at the dimensional modeling stage — e.g. two ontology entities that would produce identical dimension tables. Do **not** re-open concept collapses already confirmed in `taxonomy.json`; those are settled.

If a new collapse is warranted, confirm with the user before merging the tables.

### 6. Write CDM

Write `.schema/CDM.dbml` using DBML syntax. Encode metadata in `Table` notes:

```dbml
Table dim_person [note: 'table_type:dimension; surrogate_key:person_sk; scd_type:1; conformed:true'] {
  person_sk bigint [pk, note: 'surrogate key']
  source_id varchar [note: 'source key — original ID from the upstream system, stored for lineage']
  source_pipeline varchar
  email varchar
  first_name varchar
  last_name varchar
  company_sk bigint [ref: > dim_company.company_sk]
}

Table fact_event_attendance [note: 'table_type:fact; grain:one row per person per event attended'] {
  attendance_sk bigint [pk]
  person_sk bigint [ref: > dim_person.person_sk]
  event_sk bigint [ref: > dim_event.event_sk]
  registered_at timestamp
  attended bool
}
```

Required `note` fields per table type:
- **Dimension**: `table_type`, `surrogate_key`, `scd_type`, `conformed`
- **Fact**: `table_type`, `grain`

## Output

- `.schema/<cdm-name>/CDM.dbml` — implementation-ready CDM schema

After writing the file, explicitly ask the user to open and review `.schema/<cdm-name>/CDM.dbml` before continuing:

```
Please review `.schema/<cdm-name>/CDM.dbml` — it contains the full data model with all tables, columns, and relationships.

Let me know if anything looks wrong or needs changing before we move on.
```

Wait for explicit confirmation before handing over to `create-transformation` skill.

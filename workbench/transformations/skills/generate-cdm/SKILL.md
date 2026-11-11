---
name: generate-cdm
description: Generate a Canonical Data Model (CDM) in DBML using Kimball dimensional modeling. Use after create-ontology to produce the implementation-ready CDM schema.
---

# Generate CDM

## Prerequisites
Skip this if you already checked it in this session.
1. Run `uv --version`. If it fails, `uv` is missing.
   - Ask the user to allow the `uv` install. Do not install it without approval.
   - On macOS and Linux, run `curl -LsSf https://astral.sh/uv/install.sh | sh`.
   - On Windows, run `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.
   - Docs: https://docs.astral.sh/uv/getting-started/installation/
   - If `uv` is still not found, tell the user to open a new shell, because the install changes `PATH`.
2. Run `uv run dlthub ai status`. If it fails, `dlt[hub]` or the dlthub workspace is missing.
3. Check that these skills are available. If a skill is not available, its toolkit is missing.
   - `setup-secrets` from the `init` toolkit
   - `setup-runtime` from the `dlthub-platform` toolkit
   - Do not check the `dlt-workspace-mcp` tools. They do not start without `dlt[hub]`.
4. Find how this skill was installed. Look at the folder of this skill.
   - The folder is in the project (`.claude/`, `.cursor/` or `.agents/`): the `dlthub` CLI installed it.
   - The folder is not in the project: a plugin marketplace installed it.
5. If anything is missing, tell the user that this skill does not work without it.
   - Ask the user to allow each install.
   - Install from the same channel as this skill. Then each toolkit has only one copy.
6. The `dlthub` CLI installed this skill:
   - If `dlt[hub]` or `init` is missing, run `uvx dlthub-init@latest`. It installs both.
   - For each other missing toolkit, run `uv run dlthub --non-interactive ai toolkit install <toolkit>`.
7. A plugin marketplace installed this skill:
   - If `dlt[hub]` or the workspace is missing, run `uvx --from "dlt[hub]" dlthub init`.
   - Do not run `uvx dlthub-init@latest`. It adds a second copy of `init`.
   - Ask the user to install each missing toolkit from the same marketplace.
   - In Claude Code, the command is `/plugin install <toolkit>@dlthub-ai-harness`.
8. After the install, tell the user to restart the session. Skills, rules and MCP load only at session start.
9. If the user refuses an install, stop. Do not run other steps of this skill.

Translate the ontology into an implementation-ready Canonical Data Model using Kimball dimensional modeling.

**Requires** `.schema/<cdm-name>/ontology.ison` from `create-ontology`.
If missing, run `create-ontology` first.

Read `_name` from `.schema/<cdm-name>/taxonomy.json` to determine `<cdm-name>` — all files in this skill are under that folder.

Reference: DBML format — https://dbml.dbdiagram.io/

## Steps

### 1. Classify entities as fact or dimension

Read `.schema/<cdm-name>/ontology.ison`. For each entity, apply Kimball classification:

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

Write `.schema/<cdm-name>/CDM.dbml` using DBML syntax. Encode metadata in `Table` notes:

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

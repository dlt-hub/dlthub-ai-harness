---
name: check-taxonomy
description: Check whether x-taxonomy annotations are still in sync with the current dlt schema. Use when the pipeline schema has evolved (new endpoints, columns added/removed), when taxonomy.md has been edited, or before re-annotating an existing CDM.
---

# Check taxonomy

Detect drift between the `x-taxonomy` annotations written into dlt schema JSONs and the current state of the pipeline schemas. Surface mismatches for the user to resolve before design or transformation work continues.

**When to run:**
- Pipeline has been re-run and new tables or columns appeared
- `taxonomy.md` was edited directly (concept renamed, table reassigned, natural key changed)
- User wants to add a new source to an existing CDM
- `annotate-sources` detects existing annotations and prompts this skill

**Requires:**
- `~/.dlt/pipelines/<pipeline_name>/schemas/<pipeline_name>.schema.json` — with existing `x-taxonomy` blocks
- `.schema/<cdm-name>/taxonomy.md` — current concept definitions
- `.schema/<cdm-name>/ontology.md` — attribute list per entity (to check column-level drift)

If no `x-taxonomy` annotations exist yet, there is nothing to check — run `annotate-sources` instead.

## Steps

### 1. Discover annotated pipelines

Run a Python script to find all pipelines that have `x-taxonomy` annotations and collect their current state:

```python
"""Collect x-taxonomy annotations and current schema state for drift detection."""
import json
from pathlib import Path

# Replace with pipeline names from session context or taxonomy.md Pipeline: header
pipeline_names = ["<pipeline_name_1>", "<pipeline_name_2>"]

report = {}
for pipeline_name in pipeline_names:
    schema_path = Path.home() / ".dlt" / "pipelines" / pipeline_name / "schemas" / f"{pipeline_name}.schema.json"
    if not schema_path.exists():
        report[pipeline_name] = {"error": "schema file not found"}
        continue

    schema = json.loads(schema_path.read_text())
    tables = schema.get("tables", {})

    annotated = {}   # tables with x-taxonomy
    unannotated = [] # tables without x-taxonomy (excluding _dlt_*)

    for table_name, table in tables.items():
        if table_name.startswith("_dlt"):
            continue
        if "x-taxonomy" in table:
            annotated[table_name] = {
                "taxonomy": table["x-taxonomy"],
                "columns": list(table.get("columns", {}).keys()),
            }
        else:
            unannotated.append(table_name)

    report[pipeline_name] = {
        "annotated": annotated,
        "unannotated": unannotated,
    }

print(json.dumps(report, indent=2))
```

Run with `uv run python tools/check_taxonomy.py`. Use the output as the basis for all drift checks below.

### 2. Check for structural drift

For each annotated table, identify the following drift types:

**A — Natural key column missing**
The `natural_key` recorded in `x-taxonomy` no longer exists as a column in the schema. This is critical — cross-source linking will silently break.

**B — New tables with no annotation**
Tables exist in the current schema but have no `x-taxonomy`. These may represent new API endpoints or resources added since the CDM was designed. They might map to an existing concept or introduce a new one.

**C — Annotated tables that no longer exist**
A table recorded in `x-taxonomy` is no longer in the schema. The pipeline may have been restructured or the endpoint removed.

### 3. Check for taxonomy.md drift

Read `.schema/<cdm-name>/taxonomy.md`. Extract the concept names from the `## Concepts` section (each `### {Concept Name}` heading is a concept).

Compare against the set of `concept` values across all `x-taxonomy` blocks:

**D — Concept in taxonomy.md with no annotated tables**
A concept is defined in the business review document but no source table maps to it. May indicate a table was dropped (see C), or taxonomy.md was edited to add a new concept that hasn't been annotated yet.

**E — Concept in x-taxonomy with no entry in taxonomy.md**
An annotation references a concept that was removed or renamed in taxonomy.md. The annotation is now orphaned.

### 4. Check for ontology drift

Read `.schema/<cdm-name>/ontology.md`. For each entity's attribute table, check whether the listed columns still exist on the source table in the current schema:

**F — Attribute in ontology.md no longer exists as a column**
The ontology references a column that has been renamed or removed. The transformation SQL will fail if it selects this column.

### 5. Present drift report

Present a consolidated report to the user, grouped by severity:

```
Taxonomy drift report
─────────────────────

CRITICAL (will break transformation):
  [A] hubspot_crm_pipeline / hubspot__contacts — natural key "email" column no longer exists
  [F] ontology.md / Person.email — column removed from hubspot__contacts

REVIEW NEEDED:
  [B] hubspot_crm_pipeline — 3 new unannotated tables: hubspot__deals, hubspot__tickets, hubspot__calls
  [D] taxonomy.md — concept "Deal" defined but no tables annotated

NO ACTION:
  [C] luma_pipeline / luma__legacy_guests — table no longer in schema (removed endpoint)
  [E] x-taxonomy references "Lead" — not found in taxonomy.md

What would you like to do?
```

For each item, offer the user resolution options (see step 6).

### 6. Resolve drift

Work through each issue with the user:

**For A (natural key missing):** Ask the user to confirm a replacement natural key or confirm that cross-source linking should be dropped for this concept. Update `x-taxonomy` in the schema JSON accordingly.

**For B (new unannotated tables):** For each new table, ask whether it maps to an existing concept, introduces a new concept, or should be excluded. If it maps to an existing concept, write `x-taxonomy` for it. If it introduces a new concept, prompt the user to update `taxonomy.md` and then annotate. If excluded, note why.

**For C (annotated table gone):** Remove the stale `x-taxonomy` entry is not needed — the table is gone. Update `taxonomy.md` and `ontology.md` to remove the reference if the concept no longer has any source tables.

**For D (concept in taxonomy.md, no tables):** Either the concept needs new annotation (link to an existing unannotated table or run `annotate-sources` for a new pipeline) or the concept should be removed from `taxonomy.md`. Confirm with user.

**For E (orphaned x-taxonomy concept):** Ask whether the concept was renamed in taxonomy.md. If so, update `x-taxonomy` to use the new name. If it was intentionally removed, clear the `x-taxonomy` block from the table.

**For F (ontology attribute gone):** Inform the user that `ontology.md` will need to be updated. Flag it as a required edit before running `create-transformation` — the SQL will reference a column that no longer exists.

For any schema JSON changes, write and run a patch script following the same pattern as `annotate-sources` step 7b.

### 7. Confirm and summarise

After all resolutions are applied, present a summary of what changed:

```
Resolved:
  ✓ natural key updated: hubspot__contacts → domain (was: email)
  ✓ x-taxonomy added to hubspot__deals → Deal (primary, no natural key)
  ✓ taxonomy.md updated — Deal concept added

Still needs attention:
  ! ontology.md — Person.email attribute removed; update before running create-transformation
  ! CDM.md — if dim_person referenced email as a column, update before running create-transformation

Next step: update ontology.md and CDM.md to reflect the resolved drift, then re-run create-transformation.
```

## Output

- `~/.dlt/pipelines/<pipeline_name>/schemas/<pipeline_name>.schema.json` — `x-taxonomy` blocks updated where drift was resolved
- `.schema/<cdm-name>/taxonomy.md` — updated if concepts were added, renamed, or removed
- No new files created — this skill only reconciles existing artifacts
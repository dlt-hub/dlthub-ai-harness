---
name: validate-terminology
description: Scan a toolkit for terminology divergences against the dlt controlled vocabulary. Use when the user asks to check terminology, validate terms, review glossary compliance, or ensure skills use correct dlt vocabulary.
argument-hint: "<toolkit-name-or-path>"
---

# Validate Terminology

Scan all skills, commands, and rules in a toolkit for terminology issues against the [dlt controlled vocabulary](/.vocabulary/vocabulary.md).

## Step 0: Parse arguments

`$ARGUMENTS` should be a toolkit name (e.g., `rest-api-pipeline`) or path to a toolkit directory.

- If bare name, resolve to `workbench/<name>/`
- If path, use directly
- If empty, ask the user which toolkit to scan

Verify the toolkit directory exists.

## Step 1: Load vocabulary

Read the base vocabulary at [vocabulary.md](/.vocabulary/vocabulary.md). Also check for a toolkit overlay at `<toolkit>/.vocabulary/vocabulary.md` — it may promote certain deprecated terms to acceptable alternatives and define toolkit-specific terms. Extract:
- The **Deprecated Term Index** (Section 4) — terms to flag and their preferred replacements
- The **Controlled Vocabulary** (Section 2) — for precision checks
- The **Workspace Actions** (Section 3) — canonical action-object pairs
- The **Workflow Steps** (Section 3) — canonical step names

## Step 2: Collect files to scan

Glob the toolkit for all markdown content:
- `skills/*/SKILL.md` and sibling `*.md` files
- `commands/*.md`
- `rules/*.md` (including `workflow.md`)

List files found with count.

## Step 3: Scan for deprecated terms

For each file, search for deprecated/incorrect terms (case-insensitive, word-boundary aware):

| Pattern | Issue | Preferred |
|---------|-------|-----------|
| `ETL job` | deprecated pipeline synonym | **pipeline** |
| `data flow` (meaning pipeline) | deprecated synonym | **pipeline** |
| `source connector` | deprecated source synonym | **source** |
| `\btap\b` (meaning dlt source) | deprecated synonym | **source** |
| `\badapter\b` (meaning dlt source) | deprecated synonym | **source** |
| `\bstream\b` (meaning dlt resource) | deprecated synonym | **resource** |
| `\boverwrite\b` (as write disposition) | deprecated value | **replace** |
| `\bupsert\b` (as write disposition) | deprecated value | **merge** |
| `\binsert\b` (as write disposition) | deprecated value | **append** |
| `\bphase\b` (for pipeline step) | deprecated synonym | **step** |
| `\bstage\b` (for pipeline step) | deprecated synonym | **step** (but "staging" is OK) |
| `delta load` | deprecated term | **incremental loading** |
| `data contract` (for schema) | deprecated synonym | **schema** |
| `extraction step` | incorrect form | **extract step** |
| `normalization step` | incorrect form | **normalize step** |
| `loading step` | incorrect form | **load step** |

**Context matters**: avoid false positives. "staging destination" is fine. "stream" in "data stream" may be OK as data iterator alternative. "tap" in URLs/code is fine. "insert" in SQL context is fine. Only flag when used *as a synonym for a dlt concept*.

## Step 4: Check entity/concept precision

Scan for imprecise usage:
1. **"database"** used where **"destination"** is meant (e.g., "load into the database")
2. **"endpoint"** used where **"resource"** is meant (endpoint backs a resource, not a synonym)
3. **"source"** used ambiguously — does it mean `@dlt.source` or external **data source**? Flag if unclear.
4. **"table"** ambiguous — **schema table**, **destination table**, or **data resource**?
5. **"schema"** used as "data model" or "contract" rather than dlt schema object

## Step 5: Validate skill names against canonical actions

Each skill name should follow the pattern `<action>-<object>` where both action and object come from the vocabulary.

### Canonical actions and valid objects

| Action | Valid Objects | Meaning |
|--------|-------------|---------|
| **create** | pipeline, report, transformation, ontology | Author new code/artifact |
| **run** | pipeline | Execute: extract -> normalize -> load |
| **debug** | pipeline, deployment | Post-run inspection of traces/errors |
| **inspect** | pipeline | Examine state, schema, configuration |
| **validate** | dataset | Verify schema, types, row counts, quality |
| **show** | pipeline, dataset, report | Display summary |
| **deploy** | workspace | Push to production runtime |
| **maintain** | pipeline, dataset, report | Ongoing production monitoring |
| **find** | source | Discovery step (pre-create) |
| **add** | resource | Add component to existing artifact |
| **annotate** | sources | Map source tables to business concepts |

### Check each skill

For every `skills/*/SKILL.md`, extract the `name:` from frontmatter and decompose into `<action>-<object>`. Flag:

1. **Unknown action**: the verb is not in the canonical list above. Report the verb and suggest the closest canonical action.
2. **Unknown object**: the noun is not a recognized glossary entity or deliverable. Report and suggest the correct entity name.
3. **Action-object mismatch**: the action exists but doesn't apply to that object type (e.g., "validate" applies to "dataset" not "data"; "debug" applies to "pipeline" not "endpoint").
4. **Non-verb name**: skill name uses an adjective or noun where a verb is expected (e.g., "new-endpoint" — "new" is not a verb).

## Step 6: Validate workflow steps

Read `rules/workflow.md` (or `workflow.md` at toolkit root). Check:

### Step names match canonical workflow

The dltHub Workspace Workflow defines these high-level steps:
1. **Create Pipeline** — author pipeline code
2. **Ensure Data Quality** — debug, inspect, validate
3. **Create Reports and Transformations** — author reports/transforms
4. **Deploy Workspace** — push to production
5. **Maintain Data Quality** — ongoing monitoring

Each toolkit workflow step should map to one of these, or be a recognized sub-step (using a canonical action). Flag steps that use non-canonical verbs or objects.

### Skill references resolve

For each skill referenced in the workflow (format: `` (`skill-name`) ``):
- Verify a matching `skills/<skill-name>/SKILL.md` exists
- Flag broken references

### Workflow completeness

Check whether the workflow covers the expected actions for its scope:
- A pipeline-building toolkit should have skills for: **find/create**, **debug**, **validate**
- Flag if **inspect** (pipeline state/schema examination) is missing as a distinct skill or explicitly covered by another skill
- Flag if **run** is embedded in other skills rather than being a distinct step (acceptable but worth noting)

## Step 7: Report

```
## Terminology Scan: <toolkit-name>

### Files scanned
- <count> files in <toolkit-path>

### Deprecated terms found
| File | Line | Found | Should be | Context |
|------|------|-------|-----------|---------|
| ...  | ...  | ...   | ...       | ...     |

(or "None found")

### Precision issues
| File | Line | Term | Issue | Suggestion |
|------|------|------|-------|------------|
| ...  | ...  | ...  | ...   | ...        |

(or "None found")

### Skill name validation
| Skill | Action | Object | Issue | Suggested Name |
|-------|--------|--------|-------|----------------|
| ...   | ...    | ...    | ...   | ...            |

(or "All skill names valid")

### Workflow validation
| Step/Reference | Issue | Suggestion |
|---------------|-------|------------|
| ...           | ...   | ...        |

- Skill references: X valid, Y broken
- Workflow completeness: [missing actions if any]

(or "Workflow valid")

### Summary
- X deprecated terms
- Y precision issues
- Z skill naming issues
- W workflow issues
- Overall: CLEAN / NEEDS REVIEW
```

# dlt Controlled Vocabulary & Taxonomy

Canonical terminology for dlt entities, workflow actions, and pipeline lifecycle. Use this controlled vocabulary to validate that skills, commands, and rules use correct and consistent terms.

**Sources**: [dlt Glossary](https://www.notion.so/dlthub/dlt-Glossary-ceb82df9f4ad44fa88cdc6d1baa892e0), [dlt Entities & Lifecycles](https://www.notion.so/dlthub/dlt-Entities-their-Lifecycles-and-Relations-2679fb8e23cf80169921c4ea069bfff8), [dltHub Glossary](https://www.notion.so/dlthub/dltHub-Glossary-2679fb8e23cf80f4901feb468cdd327a)

---

## 1. Entity Taxonomy

Hierarchy of dlt entities. Indentation = parent-child. Root level = root entities.

```
Pipeline                          # root, identified by pipeline name
  Pipeline Run                    # child, identified by run id
    Pipeline Step                 # child of run: extract | normalize | load
      Load Package Job            # child of step
    Run Trace                     # created by run
  Pipeline State                  # one per pipeline, stored in dataset
    State Version                 # child of pipeline state
  Schema                          # child of pipeline, identified by schema name
    Schema Version                # child of schema, identified by version hash
      Schema Table                # identified by table name
        Schema Column             # has data type + column hints
        Table Hint                # e.g. write_disposition, parent
        Column Hint               # e.g. primary_key, merge_key, partition, sort
      Table Chain                 # root table + all nested/child tables, ordered by ancestry
  Working Directory               # stores pipeline state and active schema versions locally

Source                            # top-level, identified by source name
  Resource                        # child, identified by resource name
    Extraction Pipe               # one per resource
      Pipe Step                   # gen (creates data) or transform step
    Resource Hint                 # becomes table/column hints in extract step
    Resource State                # part of pipeline state
  Source State                    # part of pipeline state
  Source Configuration            # identified by source section + source name

Destination                       # root, identified by destination name
  Destination Capabilities        # what the destination supports
  Dataset                         # root, identified by dataset name
    Destination Table             # physical table, synced with schema table

Load Package                      # root, identified by load id
  Load Package Job                # identified by (table name, file id, file format)
```

---

## 2. Controlled Vocabulary

Format: **Preferred Term** | alternatives (acceptable) | ~~deprecated~~ (flag if found) | definition.

### Core Entities

**pipeline**
- Alternatives: —
- ~~Deprecated: ETL job, data flow, workflow (when meaning dlt pipeline)~~
- Moves data from source into destination via extract, normalize, load steps according to schema instructions. Root entity identified by **pipeline name**.
- Python: `dlt.pipeline(pipeline_name=..., destination=..., dataset_name=...)`

**source**
- Alternatives: dlt source
- ~~Deprecated: source connector, tap, data source connector, adapter~~
- Software component (`@dlt.source`) providing access to data from a **data source** as one or more **resources**, plus metadata as a **schema**.
- Note: "source" = the `@dlt.source` component. Use **data source** for the external system.

**data source**
- Alternatives: API, external source
- External location holding data with structure, organized into **data resources**. Not a dlt object.
- Examples: Hubspot, Stripe, a PostgreSQL database, REST API, CSV files.

**resource**
- Alternatives: dlt resource
- ~~Deprecated: stream, endpoint, tap stream (as synonyms for dlt resource)~~
- Software component (`@dlt.resource`) providing access to one **data resource** as a Python iterator of **data items**. Child of **source**.
- Subtypes: **transformer** (no gen step, receives data from parent resource), **standalone resource** (defined outside source).

**data resource**
- Alternatives: table, stream, collection, endpoint, topic
- A logical grouping of data within a **data source** (e.g., a database table, an API endpoint, a spreadsheet tab).

**destination**
- Alternatives: target, data store
- ~~Deprecated: database, data lake, data warehouse (as generic synonyms for dlt destination)~~
- Where data is loaded. Root entity identified by **destination name**. Has **capabilities** and a **fingerprint**.
- Python: `dlt.pipeline(..., destination="bigquery")`

**dataset**
- Alternatives: —
- Root entity identified by **dataset name**. Has a single **schema**, materialized on a single **destination**. Contains **destination tables**.
- Python: `pipeline.dataset()` (destination-agnostic access)

**schema**
- Alternatives: —
- ~~Deprecated: manifest, data contract, metadata, policy (as direct synonyms)~~
- Describes structure of data from a **source** and provides **hints** on processing/loading. Child of **pipeline**, identified by **schema name** (= source name).
- CLI: `dlt pipeline <name> schema --format mermaid`

### Schema Sub-entities

**schema version** — child of schema, identified by **version hash**. Transitions tracked via **schema update**.

**schema table** — named entry in schema version. Has **table hints** and **schema columns**. **Incomplete table** = no columns.

**schema column** — entry in schema table with **data type** and **column hints**. **Incomplete column** = no data type.

**table chain** — root table + all its nested/child tables, ordered by ancestry.

**child table** (alt: nested table) — auto-created by normalizer for nested arrays. Named `{parent_table}__{key_name}`.

### Hints

**hint** (alt: processing instruction, loading instruction) — additional information in schema that instructs normalizer/loader. Hints are *interpreted* not *enforced* and may apply differently per destination.

**table hint** — hint on a schema table. Values: `write_disposition`, `parent`, `columns`, filters.

**column hint** — hint on a schema column. Values: `primary_key`, `merge_key`, `partition`, `sort`, `unique`, `nullable`, `data_type`.

**write disposition** — `replace` | `merge` | `append`
- ~~Deprecated values: overwrite, upsert, insert~~
- `replace` = drop and recreate on each load. `merge` = upsert using primary/merge keys. `append` = always add rows.

### Pipeline Execution

**pipeline run** (alt: run) — single execution of a pipeline. Transitions through steps: extract -> normalize -> load. Succeeds if all steps succeed; fails if any step fails.

**pipeline step** — `extract` | `normalize` | `load`
- ~~Deprecated: phase, stage (as synonyms for pipeline step)~~
- Ordered processing within a run. Each processes one or more **load packages**.

**extract step** — first step. Pulls data from **source**, creates **load packages**, adds **schema**. Only step that may create/modify **pipeline state**.

**normalize step** — second step. Converts **data items** into **loader file formats** (CSV, JSON, Avro, Parquet). May create **schema version**. Requires **destination capabilities**.

**load step** — third step. Sends **load packages** to **destination**. Syncs schema, may create dataset, loads data.

**run trace** (alt: trace) — execution timeline/diagnostics for a pipeline run.
- CLI: `dlt pipeline -vv <name> trace` (flags BEFORE pipeline name)

### Load Package

**load package** — root entity identified by **load id** (strictly increasing). Contains one **schema version** and one or more **jobs**.
- States: `new` -> `extracted` -> `normalized` -> `loaded` | `aborted`
- Groupings: **pending** (extracted/normalized), **completed** (loaded/aborted)
- CLI: `dlt pipeline <name> load-package [load_id]`

**job** (load package job)
- States: `new_jobs` -> `started_jobs` -> `completed_jobs` | `failed_jobs`
- Data for one **schema table**. Identified by (table name, file id, file format).
- CLI: `dlt pipeline <name> failed-jobs`

### Pipeline State & Configuration

**pipeline state** — persistent state visible to sources, stored in **dataset**. Contains source/resource states. Powers incremental loading.
- CLI: `dlt pipeline -v <name> info`

**incremental loading** (alt: incremental)
- ~~Deprecated: delta load~~
- Loading only new/changed data using a cursor column via `dlt.sources.incremental`.

**dev mode** — dataset name gets serial number, working directory emptied. Fresh dataset each run.
- Python: `dlt.pipeline(..., dev_mode=True)`

**refresh run** — subtypes: **source refresh** (drops source state + schema + tables), **resource refresh** (selective), **data refresh** (truncates tables + removes resource state).

### Data Flow

**data item** (alt: event, item, row) — single instance of data from the source.

**data iterator** (alt: data, data stream) — Python iterator of **data items** produced by a **resource**.

**processing step** (resource-level) — `map` | `filter` | `yield_map` — in-resource transforms during extract.

### Pipeline Components

**extractor** (alt: source extractor) — component that extracts data and schema from source/resource.

**normalizer** (alt: normaliser) — component that normalizes data items per schema into loader file formats.

**loader** (alt: destination loader) — component that sends load packages to destination.

---

## 3. dltHub Workspace Workflow Vocabulary

### Workflow Steps (canonical order)

| # | Step Name | Deliverable | Key Action Verbs |
|---|-----------|-------------|-----------------|
| 1 | **Create Pipeline** | Pipeline (Python code) | create, scaffold |
| 2 | **Ensure Data Quality** | Dataset (data + schema) | debug, inspect, validate |
| 3 | **Create Reports and Transformations** | Report Notebook, Transformations | create, transform |
| 4 | **Deploy Workspace** | Deployed deliverables | deploy |
| 5 | **Maintain Data Quality** | Deployed reports | maintain, monitor |

### Workspace Actions (canonical verbs)

These are the canonical action-object pairs for naming skills, workflow steps, and section headers.

| Action | Valid Objects | Meaning |
|--------|-------------|---------|
| **create** | pipeline, report, transformation, ontology | Author new code/artifact |
| **run** | pipeline | Execute: extract -> normalize -> load |
| **find** | source | Discover the right source for a data provider |
| **debug** | pipeline, deployment | Inspect traces, load packages, exceptions after a failed/suspect run |
| **inspect** | pipeline | Examine pipeline state, schema, configuration |
| **validate** | dataset | Verify schema correctness, data types, row counts, quality after load |
| **show** | pipeline, dataset, report | Display summary |
| **add** | resource | Add a component to an existing artifact |
| **adjust** | resource | Harden a resource for production (pagination, incremental, limits) |
| **annotate** | sources | Map source tables to business concepts |
| **deploy** | workspace | Push to production runtime |
| **maintain** | pipeline, dataset, report | Ongoing production monitoring |

### Skill naming convention

Skills should be named `<action>-<object>` using the canonical actions and objects above.

**Rules:**
1. The **action** must be a verb from the table above.
2. The **object** must be a recognized glossary entity or deliverable.
3. The action must be valid for that object type (e.g., **validate** applies to **dataset** not "data").
4. Adjectives and nouns are not valid actions (e.g., "new" is not a verb — use **add** or **create**).

---

## 4. Deprecated Term Index

Quick-reference of terms to flag during validation. Left = deprecated/incorrect, right = preferred.

| Flag if found | Preferred term |
|--------------|----------------|
| ETL job, data flow | pipeline |
| source connector, tap, adapter | source |
| stream (for dlt resource) | resource |
| overwrite | replace (write disposition) |
| upsert | merge (write disposition) |
| insert (as write disposition) | append |
| phase, stage (for pipeline step) | step (extract/normalize/load) |
| delta load | incremental loading |
| manifest, data contract | schema |
| database (as generic for destination) | destination |
| extraction step | extract step |
| normalization step | normalize step |
| loading step | load step |

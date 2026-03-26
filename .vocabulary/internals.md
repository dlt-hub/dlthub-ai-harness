# dlt Internal Concepts

Implementation-level entities describing how dlt works internally. Not used in toolkit skills or user-facing workflows. Separated from the [main vocabulary](vocabulary.md) to keep validation and diagrams focused on operational concepts.

Load with `--include-internals` in validator/visualizer.

---

## Schema Details (below `schema`)

**schema version** — child of schema, identified by **version hash**. Transitions tracked via **schema update**.

**schema table** — named entry in schema version. Has **table hints** and **schema columns**. **Incomplete table** = no columns.

**schema column** — entry in schema table with **data type** and **column hints**. **Incomplete column** = no data type.

**table chain** — root table + all its nested/child tables, ordered by ancestry.

**table hint** — hint on a schema table. Values: `write_disposition`, `parent`, `columns`, filters.

**column hint** — hint on a schema column. Values: `primary_key`, `merge_key`, `partition`, `sort`, `unique`, `nullable`, `data_type`.

## Data Flow Abstractions

**data item** (alt: event, item, row) — single instance of data from the source.

**data iterator** (alt: data, data stream) — Python iterator of **data items** produced by a **resource**.

**data resource** (alt: table, stream, collection, endpoint, topic) — a logical grouping of data within a **data source**.

## Pipeline Components

**extractor** (alt: source extractor) — component that extracts data and schema from source/resource.

**normalizer** (alt: normaliser) — component that normalizes data items per schema into loader file formats.

**loader** (alt: destination loader) — component that sends load packages to destination.

**pipeline step** — `extract` | `normalize` | `load`. Ordered processing within a run.
- ~~Deprecated: phase, stage~~

**normalize step** — second step. Converts data items into loader file formats.

**load step** — third step. Sends load packages to destination.

## Subsidiary Entities

**extraction pipe** — one per resource. Has one or more pipe steps.

**resource hint** — becomes table/column hints in extract step.

**source configuration** — identified by source section + source name.

**destination capabilities** — what the destination supports.

**destination table** — physical table at destination, synced with schema table.

**state version** — child of pipeline state.

**working directory** — stores pipeline state and active schema versions locally.

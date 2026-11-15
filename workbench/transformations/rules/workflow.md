# Transformations workflow

## Workflow Entry
**ALWAYS** start with **Annotate sources** (`annotate-sources`) SKILL — identify pipelines, extract schemas, map tables to canonical concepts, and confirm natural keys before any design work

## Core workflow
1. **Annotate sources** (`annotate-sources`) — verify pipelines exist, extract source schemas, derive canonical concepts from use cases, map tables to concepts, identify cross-source natural keys
2. **Create ontology** (`create-ontology`) — build the entity graph: one entity per concept, union attributes from all contributing sources, define relationships from natural keys and FKs
3. **Generate CDM** (`generate-cdm`) — apply Kimball dimensional modeling: classify fact/dimension, define grain, surrogate keys, SCD types, conformed dimensions
4. **Create transformation** (`create-transformation`) — write SQL-first `@dlt.hub.transformation` functions (with optional ibis) that map source tables to CDM entities

## Extend and harden

5. **Incremental transformation** (`incremental-transformation`) — switch replace→incremental when data volume grows or transformation runs are scheduled frequently; processes only new/changed rows instead of reprocessing all data
6. **Debug transformation** (`debug-transformation`) — diagnose SQL dialect incompatibility, fix failing transformations, validate portability across destinations, recover from pipeline state errors

## Handover to other toolkits

### Incoming (to transformations)

- From **data-exploration** — the profiled tables, natural key candidates and data quality observations of the exploration session carry into `annotate-sources`. Re-confirm each one with the user.
- From **data-quality** — the failing tables and check results are known: `annotate-sources` focuses on those tables.
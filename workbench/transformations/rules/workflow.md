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

## Incoming

- From **rest-api-pipeline** (after `validate-data` or `view-data`) — pipeline name, destination, and dataset are already known. `annotate-sources` should skip `list_pipelines` discovery and go straight to schema extraction on the known pipeline. Business context may already be available from the ingestion session.
- From **sql-database-pipeline** (after `validate-sql-database-data` or `view-sql-database-data`) — pipeline name, destination, and dataset are already known. `annotate-sources` should skip `list_pipelines` discovery and go straight to schema extraction on the known pipeline.
- From **data-exploration** (after exploring raw pipeline data) — pipeline name, dataset, and table structure are already understood. The user has decided the raw tables need proper modeling before further analysis. `annotate-sources` can skip discovery and lean on the already-profiled table structure; natural key candidates and data quality observations from the exploration session should carry over — but always re-confirmed.
- From **data-quality** (after `review-data-quality`) — DQ failures revealed upstream modeling issues; the failing tables and check results are known. `annotate-sources` should focus on those specific tables.

## Handover to other toolkits

When the user's needs go beyond this toolkit, hand over to:

- **rest-api-pipeline**
  - At `annotate-sources` step 1, when a stated source has no local dlt pipeline yet
  - At `create-transformation` step 8 (Run), when the run fails with a pipeline state or infrastructure error and the source is a REST API — use the `debug-pipeline` skill
- **sql-database-pipeline**
  - At `annotate-sources` step 1, when a stated SQL database source has no local dlt pipeline yet — start at `find-sql-database-source`
  - At `create-transformation` step 8 (Run), when the run fails with a pipeline state or infrastructure error and the source is a SQL database — use the `debug-sql-database-pipeline` skill
- **data-exploration** — after `create-transformation`, when the user wants to explore, visualise, or validate the CDM output interactively
- **data-quality** — after `create-transformation`, when the user wants to add quality checks on the transformed tables
- a platform toolkit — after `create-transformation` or `debug-transformation`, when the user wants to deploy, schedule or run the transformations in production: follow the workflow entry of the installed platform toolkit, carrying the transformation scripts and the destination. When none is installed, `dlthub-router` installs one
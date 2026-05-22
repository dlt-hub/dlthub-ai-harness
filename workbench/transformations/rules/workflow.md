# Transformations workflow

## Workflow Entry
**ALWAYS** start with **Annotate sources** (`annotate-sources`) SKILL — identify pipelines, extract schemas, map tables to canonical concepts, and confirm natural keys before any design work

## Core workflow
1. **Annotate sources** (`annotate-sources`) — verify pipelines exist, extract source schemas, derive canonical concepts from use cases, map tables to concepts, identify cross-source natural keys
2. **Create ontology** (`create-ontology`) — build the entity graph: one entity per concept, union attributes from all contributing sources, define relationships from natural keys and FKs
3. **Generate CDM** (`generate-cdm`) — apply Kimball dimensional modeling: classify fact/dimension, define grain, surrogate keys, SCD types, conformed dimensions
4. **Create transformation** (`create-transformation`) — write SQL-first `@dlt.hub.transformation` functions (with optional ibis) that map source tables to CDM entities

## Extend and harden
5. **Debug transformation** (`debug-transformation`) — diagnose SQL dialect incompatibility, fix failing transformations, validate portability across destinations, recover from pipeline state errors

## Incoming

- From **rest-api-pipeline** (after `validate-data` or `view-data`) — pipeline name, destination, and dataset are already known. `annotate-sources` should skip `list_pipelines` discovery and go straight to schema extraction on the known pipeline. Business context may already be available from the ingestion session.
- From **sql-database-pipeline** (after `validate-data` or `view-data`) — pipeline name, destination, and dataset are already known. `annotate-sources` should skip `list_pipelines` discovery and go straight to schema extraction on the known pipeline.
- From **data-exploration** (after exploring raw pipeline data) — pipeline name, dataset, and table structure are already understood. The user has decided the raw tables need proper modeling before further analysis. `annotate-sources` can skip discovery and lean on the already-profiled table structure; natural key candidates and data quality observations from the exploration session should carry over — but always re-confirmed.
- From **dlthub-runtime** (during `prepare-deployment` or `deploy-workspace`) — when the prod destination differs from dev and SQL dialect errors surface. Go to `debug-transformation` section 1 (static dialect check) with the dev and prod destination types already known.
- From **data-quality** (after `review-data-quality`) — DQ failures revealed upstream modeling issues; the failing tables and check results are known. `annotate-sources` should focus on those specific tables.

## Handover to other toolkits

When the user's needs go beyond this toolkit, hand over to:

- **rest-api-pipeline**
  - At `annotate-sources` step 1, when a stated source has no local dlt pipeline yet
  - At `create-transformation` step 8 (Run), when the run fails with a pipeline state or infrastructure error — use the `debug-pipeline` skill
- **data-exploration** — after `create-transformation`, when the user wants to explore, visualise, or validate the CDM output interactively
- **dlthub-platform** — when the transformation is working and the user wants to deploy or schedule it on the dltHub platform
- **data-quality** — after `create-transformation`, when the user wants to add quality checks on the transformed tables
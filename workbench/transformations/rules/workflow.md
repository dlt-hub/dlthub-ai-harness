# Transformations workflow

## Workflow Entry
**ALWAYS** start with **Annotate sources** (`annotate-sources`) SKILL — identify pipelines, extract schemas, map tables to canonical concepts, and confirm natural keys before any design work

## Core workflow
1. **Annotate sources** (`annotate-sources`) — verify pipelines exist, extract source schemas, derive canonical concepts from use cases, map tables to concepts, identify cross-source natural keys
2. **Create ontology** (`create-ontology`) — build the entity graph: one entity per concept, union attributes from all contributing sources, define relationships from natural keys and FKs
3. **Generate CDM** (`generate-cdm`) — apply Kimball dimensional modeling: classify fact/dimension, define grain, surrogate keys, SCD types, conformed dimensions
4. **Create transformation** (`create-transformation`) — write SQL-first `@dlt.hub.transformation` functions (with optional ibis) that map source tables to CDM entities

## Incoming

- From **rest-api-pipeline** (after `validate-data` or `view-data`) — pipeline name, destination, and dataset are already known. `annotate-sources` should skip `list_pipelines` discovery and go straight to schema extraction on the known pipeline. Business context may already be available from the ingestion session.
- From **sql-database-pipeline** (after `validate-data` or `view-data`) — pipeline name, destination, and dataset are already known. `annotate-sources` should skip `list_pipelines` discovery and go straight to schema extraction on the known pipeline.
- From **data-exploration** (after exploring raw pipeline data) — pipeline name, dataset, and table structure are already understood. The user has decided the raw tables need proper modeling before further analysis. `annotate-sources` can skip discovery and lean on the already-profiled table structure; natural key candidates and data quality observations from the exploration session should carry over — but always re-confirmed.
- From **data-quality** (after `review-data-quality`) — DQ failures revealed upstream modeling issues; the failing tables and check results are known. `annotate-sources` should focus on those specific tables.
- From **quick-start** (shortcut path when a pipeline already exists) — pipeline name may be inferred from `dlt ai status`. `annotate-sources` should still confirm pipelines and use cases; no shortcuts to schema extraction unless `dlt ai status` shows a single loaded pipeline.

## Handover to other toolkits

When the user's needs go beyond this toolkit, hand over to:

- **rest-api-pipeline** — at `annotate-sources` step 1, when a stated source has no local dlt pipeline yet
- **data-exploration** — after `create-transformation`, when the user wants to explore, visualise, or validate the CDM output interactively
- **dlthub-platform** — when the transformation is working and the user wants to deploy or schedule it on the dltHub platform
- **data-quality** — after `create-transformation`, when the user wants to add quality checks on the transformed tables
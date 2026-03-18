# Transformations workflow

## Workflow Entry
**ALWAYS** start with **Annotate sources** (`annotate-sources`) SKILL — identify pipelines, extract schemas, map tables to canonical concepts, and confirm natural keys before any design work

## Core workflow
1. **Annotate sources** (`annotate-sources`) — verify pipelines exist, extract source schemas, derive canonical concepts from use cases, map tables to concepts, identify cross-source natural keys
2. **Create ontology** (`create-ontology`) — build the entity graph: one entity per concept, union attributes from all contributing sources, define relationships from natural keys and FKs
3. **Generate CDM** (`generate-cdm`) — apply Kimball dimensional modeling: classify fact/dimension, define grain, surrogate keys, SCD types, conformed dimensions
4. **Create transformation** (`create-transformation`) — write `@dlt.hub.transformation` ibis functions that map source tables to CDM entities

## Handover to other toolkits

When the user's needs go beyond this toolkit, hand over to:

- **rest-api-pipeline** — at `annotate-sources` step 1, when a stated source has no local dlt pipeline yet
- **data-exploration** — after `create-transformation`, when the user wants to explore, visualise, or validate the CDM output interactively
- **dlthub-runtime** — when the transformation is production-ready and the user wants to schedule or deploy it on the dltHub platform
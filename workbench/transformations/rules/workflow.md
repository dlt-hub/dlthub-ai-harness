# Transformations workflow

## Workflow Entry
**ALWAYS** start with **Annotate sources** (`annotate-sources`) SKILL — identify pipelines, extract schemas, map tables to canonical concepts, and confirm natural keys before any design work

## Core workflow
1. **Annotate sources** (`annotate-sources`) — verify pipelines exist, extract source schemas, derive canonical concepts from use cases, map tables to concepts, identify cross-source natural keys, and write initial `.schema/<cdm-name>/ontology_model.py`
2. **Create ontology** (`create-ontology`) — enrich `.schema/<cdm-name>/ontology_model.py` with typed entity classes, merge policies, and relationship edges derived from natural keys + FKs
3. **Generate CDM** (`generate-cdm`) — read `.schema/<cdm-name>/ontology_model.py` and apply Kimball dimensional modeling: classify fact/dimension, define grain, surrogate keys, SCD types, conformed dimensions
4. **Create transformation** (`create-transformation`) — write SQL-first `@dlt.hub.transformation` functions (with optional ibis) that map source tables to CDM entities

## Handover to other toolkits

When the user's needs go beyond this toolkit, hand over to:

- **rest-api-pipeline** — at `annotate-sources` step 1, when a stated source has no local dlt pipeline yet
- **data-exploration** — after `create-transformation`, when the user wants to explore, visualise, or validate the CDM output interactively
- **dlthub-runtime** — when the transformation is production-ready and the user wants to schedule or deploy it on the dltHub platform
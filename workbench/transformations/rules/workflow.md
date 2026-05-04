# Transformations workflow

## Workflow Entry
**ALWAYS** start with **Annotate sources** (`annotate-sources`) SKILL — identify pipelines, extract schemas, map tables to canonical concepts, and confirm natural keys before any design work

## Core workflow
1. **Annotate sources** (`annotate-sources`) — verify pipelines exist, read source schemas, derive canonical concepts from use cases, map tables to concepts, identify cross-source natural keys
   - Writes `x-taxonomy` blocks into `~/.dlt/pipelines/<pipeline>/schemas/<pipeline>.schema.json` (versioned alongside the structural schema)
   - Writes `.schema/<cdm-name>/taxonomy.md` (business-facing model review document)
2. **Create ontology** (`create-ontology`) — build the entity graph: one entity per concept, union attributes from all contributing sources, define relationships from natural keys and FKs
   - Reads schema JSONs (`x-taxonomy`) + `taxonomy.md`
   - Writes `.schema/<cdm-name>/ontology.md` (developer-facing entity graph summary)
3. **Generate CDM** (`generate-cdm`) — apply Kimball dimensional modeling: classify fact/dimension, define grain, surrogate keys, SCD types, conformed dimensions
   - Reads `ontology.md`
   - Writes `.schema/<cdm-name>/CDM.md` (Mermaid ERD + per-table column specs)
4. **Create transformation** (`create-transformation`) — write SQL-first `@dlt.hub.transformation` functions (with optional ibis) that map source tables to CDM entities
   - Reads schema JSONs (`x-taxonomy`) + `taxonomy.md` + `CDM.md`
   - Writes `transformations/<dataset_name>_to_cdm.py`

## Conditional: schema or taxonomy has evolved

Run **Check taxonomy** (`check-taxonomy`) when:
- The pipeline has been re-run and new tables or columns appeared since the CDM was designed
- `taxonomy.md` was edited directly (concept renamed, table reassigned, natural key changed)
- A new source is being added to an existing CDM

`annotate-sources` will prompt this automatically when it detects existing `x-taxonomy` annotations on a pipeline. `check-taxonomy` can also be invoked directly at any time.

## Incoming

- From **rest-api-pipeline** (after `validate-data` or `view-data`) — pipeline name, destination, and dataset are already known. `annotate-sources` should skip `list_pipelines` discovery and go straight to schema extraction on the known pipeline. Business context may already be available from the ingestion session.
- From **data-exploration** (after exploring raw pipeline data) — pipeline name, dataset, and table structure are already understood. The user has decided the raw tables need proper modeling before further analysis. `annotate-sources` can skip discovery and lean on the already-profiled table structure; natural key candidates and data quality observations from the exploration session should carry over — but always re-confirmed.

## Handover to other toolkits

When the user's needs go beyond this toolkit, hand over to:

- **rest-api-pipeline** — at `annotate-sources` step 1, when a stated source has no local dlt pipeline yet
- **data-exploration** — after `create-transformation`, when the user wants to explore, visualise, or validate the CDM output interactively
- **dlthub-runtime** — when the transformation is working and the user wants to deploy or schedule it on the dltHub platform
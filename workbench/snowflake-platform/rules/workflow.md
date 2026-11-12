# Snowflake and Cortex Code workflow

This toolkit is for the Cortex Code agent (CoCo) that works on a dlt project with Snowflake as the destination.

## Workflow Entry
**ALWAYS** start with **Set up the Snowflake destination** (`setup-snowflake-destination`) SKILL — configure credentials, naming convention and type pins, then verify that the pipeline loads into Snowflake

## Core workflow
1. **Set up the Snowflake destination** (`setup-snowflake-destination`) — key-pair or PAT credentials, account identifier, naming convention, type pins, staging and replace behaviour, and the Snowflake-specific load errors
2. **Annotate with Cortex** (`annotate-with-cortex`) — add a follow-up job that calls the Cortex Agents REST API: the agent profiles the loaded tables, the job writes table and column comments, creates a semantic view and loads the agent's report

## Extend and harden
3. **Take over existing tables** (`setup-snowflake-destination`) — when another tool wrote the tables: match identifiers and types, clone with `COPY GRANTS`, backfill the `_dlt_*` columns (`references/existing-tables.md` in the skill)
4. Query the semantic view from Cortex Analyst — planned

## Handover to other toolkits

### Outgoing (from snowflake-platform)

- **dlthub-platform** → `setup-runtime` — from (`annotate-with-cortex`), when the annotation job must be deployed. It is a dependency of this toolkit, so it is installed already. The pipeline name, dataset and the job module are known, so skip discovery. Then `prepare-deployment` and `deploy-workspace`
- **transformations** → `create-ontology` — from (`annotate-with-cortex`), when the user has no business context yet and wants an ontology that the Cortex agent keeps word for word
- **rest-api-pipeline** → `find-source` — when there is no pipeline that loads into Snowflake yet and the source is a REST API

### Incoming (to snowflake-platform)

- From a pipeline toolkit (**rest-api-pipeline**, **sql-database-pipeline**, **filesystem-pipeline**) — the pipeline works on a local destination and must move to Snowflake; carry the pipeline name and dataset into `setup-snowflake-destination`
- From **transformations** (after `create-ontology`) — the ontology tables are in the warehouse; carry the dataset into `annotate-with-cortex`

References:
* **dlt Snowflake destination**: https://dlthub.com/docs/dlt-ecosystem/destinations/snowflake.md
* **Cortex Code**: https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code
* **Cortex Agents REST API**: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-rest-api
* **Semantic views**: https://docs.snowflake.com/en/user-guide/views-semantic/overview

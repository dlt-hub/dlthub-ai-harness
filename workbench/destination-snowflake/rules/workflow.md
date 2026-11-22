# Snowflake as a destination

This is the destination toolkit of Snowflake: loading into Snowflake and what is around it, the connection, the
business and semantic context the account already has, and the semantic views and dynamic tables built from the
ontology and the CDM. Deploying and running jobs belongs to a platform toolkit. The files of this toolkit live next to
the model they belong to, in `.dlthub/ontology/<name>/`.

Snowflake destination intents go to the skills of this toolkit, which are installed already. They win over
`dlthub-router` for these intents; install nothing. Snowflake objects that dlthub does not create (streams, other
tasks, the tables of other teams) are not ours: Cortex Code and its bundled skills know the Snowflake internals.

## Workflow Entry
**ALWAYS** start with **Connect and load** (`setup-snowflake-destination`) when a pipeline, a profile or a production
destination is set up for Snowflake: the connection, the credentials, naming, type pins, staging and the Snowflake
load errors.

## Where this toolkit joins other toolkits
Other toolkits ask for the destination toolkit at these steps. On Snowflake:
- **The destination and its credentials**: the destination of a new pipeline (`find-source`,
  `find-sql-database-source`, `create-filesystem-pipeline`), the destination credentials (`setup-secrets`) and a
  warehouse in production (`setup-profiles`, `prepare-deployment`) → (`setup-snowflake-destination`)
- **Before any pipeline or model code, and after the model**: the `Business and semantic context on Snowflake` rule
- **The model**: when `create-transformation` determines the destination or `incremental-transformation` chooses a
  pattern, offer **Dynamic tables** (`create-snowflake-dynamic-tables`) next to dlt transformations; once the CDM
  tables are in Snowflake, a **Semantic view** (`create-snowflake-semantic-view`)
- **A load that fails on Snowflake** (`troubleshoot-pipeline-run`, `debug-pipeline`) → the known failures of
  (`setup-snowflake-destination`). SQL dialect errors stay with `debug-transformation`.

## Core workflow
1. **Connect and load** (`setup-snowflake-destination`) — the connection, credentials, naming convention, type pins,
   staging and replace behaviour, the Snowflake load errors, and tables that another tool wrote
2. **Business and semantic context** (`collect-snowflake-context`) — what the account already knows before a
   pipeline or model is built
3. **Dynamic tables** (`create-snowflake-dynamic-tables`) — the CDM translated into dynamic tables that Snowflake
   refreshes on its own
4. **Semantic view** (`create-snowflake-semantic-view`) — a semantic view on the CDM, for Cortex Analyst and agents
5. **Annotate with Cortex** (`annotate-with-cortex`) — a follow-up job that calls the Cortex Agents REST API: table
   and column comments grounded in the rows, and a semantic view
6. **Hand over to Cortex Code** (`delegate-to-cortex-code`), outside Cortex Code — a Snowflake task that needs the
   Snowflake internals runs in Cortex Code as a subagent

## Ask first
Dynamic tables refresh on a warehouse on their own schedule and spend credits. Never create one, or change its
target lag or warehouse, without the user's explicit yes. Show what refreshes and how often.

References:
* **dlt Snowflake destination**: https://dlthub.com/docs/dlt-ecosystem/destinations/snowflake.md
* **Dynamic tables**: https://docs.snowflake.com/en/user-guide/dynamic-tables-about
* **Cortex Agents REST API**: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-rest-api

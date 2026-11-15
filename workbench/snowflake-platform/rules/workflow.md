# Deploy to Snowflake with the SPCS Context Runner

The SPCS Context Runner runs dltHub jobs in the user's Snowflake account: each batch job is a Snowflake task, each
job run is a job service on a compute pool, and the dltHub app registers the job runs. The pipelines exist and run
locally; this workflow takes them to production.

This is the platform toolkit of the workspace. Other toolkits write platform commands without a prefix (`deploy`,
`job run`, `job logs`): here they are `dlthub snowflake` commands (`uv run dlthub snowflake --help`).

It owns `.dlthub/snowflake/` in the workspace: deploy writes its records to
`.dlthub/snowflake/deploy/<environment>/`.

## Workflow Entry
**ALWAYS** start with **Set up the Snowflake workspace** (`setup-snowflake-workspace`): the deploy connection, the
workspace name and `uv run dlthub snowflake info`. If the account has no runner yet, an admin runs
(`install-snowflake-runner`) first.

## Core workflow
1. **Set up the Snowflake workspace** (`setup-snowflake-workspace`) — the deploy connection and role, the workspace
   name, the MCP server with Snowflake tools
2. **Declare the jobs** (`prepare-deployment`, local-workspace toolkit) — **only its step 3**: the code becomes jobs
   in `__deployment__.py`. On Snowflake its steps 1–2 (destination and `prod` profile) are the next step
3. **Set up the data connection** (`setup-snowflake-data-connection`) — where the jobs load and with which role: the
   `prod` profile, and the `access` profile for jobs that only read
4. **Test the jobs locally** (`run-local-jobs`, `test-local-jobs`, local-workspace toolkit) — every job runs once on
   this machine before it deploys
5. **Deploy and run** (`deploy-snowflake-workspace`) — dry run, deploy, the first job run on Snowflake, schedules
   and triggers
6. **Daily maintenance** (`maintain-snowflake-jobs`) — job runs, logs, failures, pause, resume, cancel, secrets

## Extend and harden
7. **Environments** (`manage-snowflake-environments`) — deploy the same workspace again as `ci` or `staging`, with
   its own workspace schema, and with another data connection when needed
8. **dltHub control plane** (`connect-dlthub-control-plane`) — the organization, the remote workspaces and what the
   dltHub app shares
9. **Install the runner** (`install-snowflake-runner`) — for the account admin: the app, the pool, the warehouse,
   the grants
10. **Business and semantic context** — what the account already knows before a pipeline or model is built
    (`collect-snowflake-context`), and a semantic view on the CDM (`create-snowflake-semantic-view`); the
    `Business and semantic context on Snowflake` rule says when
11. **Snowflake as a destination** (`setup-snowflake-destination`) — credentials, naming convention, type pins,
    staging and replace behaviour, the Snowflake load errors, and tables that another tool wrote
12. **Annotate with Cortex** (`annotate-with-cortex`) — a follow-up job that calls the Cortex Agents REST API: table
    and column comments grounded in the rows, and a semantic view

## Ask first
Schedules, timeouts, the compute pool and the jobs warehouse spend credits on every job run. Never add, change or
remove them without the user's explicit yes. Show what changes and how often it runs.

## Handover to other toolkits

### Outgoing (from snowflake-platform)
- **transformations** → `debug-transformation` — SQL dialect errors in jobs on Snowflake: the local runs used another
  destination, so carry the dev and the Snowflake destination types into the dialect check

References:
* **dlt Snowflake destination**: https://dlthub.com/docs/dlt-ecosystem/destinations/snowflake.md
* **Cortex Agents REST API**: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-rest-api
* **Commands**: `uv run dlthub snowflake --help` and `uv run dlthub snowflake <command> --help`
* **Profiles and deployments**: https://dlthub.com/docs/hub/pipeline-operations/profiles.md,
  https://dlthub.com/docs/hub/pipeline-operations/deployments.md

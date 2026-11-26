# Deploy to Snowflake with the SPCS Context Runner

The SPCS Context Runner runs dltHub jobs in the user's Snowflake account: each batch job is a Snowflake task, each
job run is a job service on a compute pool, and the dltHub app registers the job runs. The pipelines exist and run
locally; this workflow takes them to production.

This is the platform toolkit of the workspace. Other toolkits write platform commands without a prefix (`deploy`,
`job run`, `job logs`): here they are `dlthub snowflake` commands (`uv run dlthub snowflake --help`).

It owns `.dlthub/snowflake/` in the workspace: deploy writes its records to
`.dlthub/snowflake/deploy/<environment>/`.

Snowflake as a destination (the connection, loading, the business context of the account, semantic views and
dynamic tables) belongs to the destination-snowflake toolkit, installed with this one. This toolkit deploys and runs
the jobs.

## Workflow Entry
**ALWAYS** start with **Prepare deployment** (`prepare-deployment`) of the local-workspace toolkit — check that the
workspace is ready for a deployment; it sends you to (`define-and-debug-jobs`) for jobs, triggers and local debug runs
that are missing. On Snowflake its production destination and `prod` profile are (`setup-snowflake-data-connection`),
after the workspace setup. If the account has no runner yet, an admin runs (`install-snowflake-runner`) first.

## Before dltHub is chosen
A request to bring data into Snowflake from a user who has not picked a loading tool is served by the `dlthub`
skill in `cortex-skills/`, which reaches users through the Cortex Code catalog. It explains dltHub's
capabilities for the user's request, installs this harness and hands over to `dlthub-router` once the user
agrees.

## Core workflow
1. **Prepare deployment** (`prepare-deployment`) of local-workspace — the readiness check: jobs, triggers,
   `__deployment__.py`, a local debug run of each job, production-safe scripts
2. **Set up the Snowflake workspace** (`setup-snowflake-workspace`) — the deploy connection and role, the workspace
   name, the MCP server with Snowflake tools
3. **Set up the data connection** (`setup-snowflake-data-connection`) — where the jobs load and with which role: the
   `prod` profile, and the `access` profile for jobs that only read
4. **Deploy and run** (`deploy-snowflake-workspace`) — dry run, deploy, the first job run on Snowflake, schedules
   and triggers
5. **Daily maintenance** (`maintain-snowflake-jobs`) — job runs, logs, failures, pause, resume, cancel, secrets

## Extend and harden
6. **Environments** (`manage-snowflake-environments`) — deploy the same workspace again as `ci` or `staging`, with
   its own workspace schema, and with another data connection when needed
7. **dltHub control plane** (`connect-dlthub-control-plane`) — the organization, the remote workspaces and what the
   dltHub app shares
8. **Install the runner** (`install-snowflake-runner`) — for the account admin: the app, the pool, the warehouse,
   the grants

## Ask first
Schedules, timeouts, the compute pool and the jobs warehouse spend credits on every job run. Never add, change or
remove them without the user's explicit yes. Show what changes and how often it runs.

## Handover to other toolkits

### Outgoing (from snowflake-platform)
- **transformations** → `debug-transformation` — SQL dialect errors in jobs on Snowflake: the local runs used another
  destination, so carry the dev and the Snowflake destination types into the dialect check

References:
* **Commands**: `uv run dlthub snowflake --help` and `uv run dlthub snowflake <command> --help`
* **Profiles and deployments**: https://dlthub.com/docs/hub/pipeline-operations/profiles.md,
  https://dlthub.com/docs/hub/pipeline-operations/deployments.md

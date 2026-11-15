---
name: prepare-deployment
description: "Use when the user wants to deploy, schedule or run pipelines, jobs or notebooks in production, or to check that the workspace is ready for a first deployment: jobs in __deployment__.py, a local debug run of each job, production-safe scripts, split dev and prod credentials, the prod profile and a production destination such as MotherDuck. Checks that the workspace is ready for a deployment and fixes what is missing, before a platform toolkit deploys."
---

# Prepare a deployment

Every deployment starts here, whatever the platform: check that the workspace is ready, fix what is missing, then
the platform toolkit deploys. A local run (`define-and-debug-jobs`) debugs a job. Only a deployment runs it in
production.

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/profiles.md |
https://dlthub.com/docs/hub/pipeline-operations/deployments.md

## 0. A platform toolkit is installed

The platform toolkit decides how the workspace deploys, and its rule changes some steps below, for example how the
`prod` profile is made. When none is installed, install one with the `dlthub-router` skill first, then come back
here.

## 1. Check that the workspace is ready

Run `dlthub local info`: it lists the jobs of `__deployment__.py` and their triggers. Go through the checks. Fix each
one that fails with the skill named, then come back.

| Check | When it fails |
|---|---|
| every pipeline, transformation or notebook that should deploy is a job listed in `__deployment__.py` | (`define-and-debug-jobs`), steps 1 and 4 |
| jobs that should run on their own have triggers; jobs whose data a refresh run must reload have auto-refresh | (`define-and-debug-jobs`), steps 2 and 3 |
| each job ran once with `dlthub local run` and succeeded | (`define-and-debug-jobs`), step 5 |
| the scripts are safe for production (below) | fix them here |
| the `prod` profile has a production destination and its credentials | steps 2 and 3, unless the rule of the platform toolkit names its own step |

**Safe for production**:
1. No `dev_mode=True` in `dlt.pipeline()`: it drops and recreates the dataset on every run.
2. No dev limits left in code: `.add_limit(N)`, `limit=N`, fixed test date ranges. Remove them, or move them into the
   config of the `dev` profile (`[jobs.<module>]` in `.dlt/dev.config.toml`).
3. `write_disposition` is what the user wants in production: `merge` or `append` for incremental loads, `replace`
   only for full refreshes.
4. Every package that the jobs import is in `pyproject.toml` and `uv.lock`: a deployment installs only those.
5. Transformations: when the production destination differs from dev, check the SQL dialect with the
   (`debug-transformation`) skill of the **transformations** toolkit first. Syntax that works on DuckDB may fail on
   BigQuery, Snowflake or Postgres.

**STOP**: show what fails and the plan, and get a yes before you edit code.

## 2. Pick the production destination

Offer to set up a production destination. If user is using `duckdb`, explain why ingested data will not survive to
be visible by notebooks: a deployed job runs on a runner whose local storage is lost after the job run.

1. If user is using `duckdb` — offer to set up **MotherDuck** as the production destination.
2. `dlt` supports most major warehouses, data lakes and pure filesystems.

## 3. Configure the `prod` profile

Use the (`setup-profiles`) skill, use case "DuckDB locally, a warehouse in production". Keep the **existing dev destination** in the `dev` profile. Configure the production destination and its credentials in the `prod` profile. User will be able to continue development as usual while deploying - with the same code! Notebooks run with the `access` profile, and so do agent jobs when `prod` has no profile with `none` data access. Until `access` has settings files, they run with `prod`. Give `access` read-only credentials at the destination, as use case "limit the data access of jobs" says.

- Change the `destination` of every script that you deploy, notebooks included, to the named destination.
- Offer to run pipeline locally (preferably in debug mode) to confirm settings. NOTE: pipeline will run on **dev** destination!
- Run a job with the `prod` profile only after the user agrees: it writes with the production credentials.
- Make sure that no placeholder values remain in the secrets of `prod`.

**STOP** before making changes. Show your **plan** and get approval from the user.

## Next

The workspace is ready. Continue with the workflow of the platform toolkit: it deploys the jobs and runs them in
production.

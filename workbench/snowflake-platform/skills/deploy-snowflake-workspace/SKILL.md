---
name: deploy-snowflake-workspace
description: "Use when declared jobs that ran locally should run on Snowflake: deploy or redeploy after a code change, the first job run there, schedules and follow-up triggers. Deploys the workspace with the SPCS Context Runner. Not for the first setup (setup-snowflake-workspace) or failed job runs (maintain-snowflake-jobs)."
argument-hint: "[job-name] [environment]"
---

# Deploy and run on Snowflake

Deploy builds a workspace image from your code, pushes it to Snowflake and creates one Snowflake task per batch
job. Then each job run is a job service that runs the image.

**Reference**: `README.md` § Daily commands · `docs/ARCHITECTURE.md` § Concept mapping and § Limitations ·
`uv run dlthub snowflake deploy --help`

Before you start, (`prepare-deployment`) found the workspace ready (the jobs, their triggers, a local debug run of each
job, production-safe scripts), and the workspace setup and the data connection are done. When one is missing, go
back to it.

## 1. What Snowflake needs on top

- **The image installs only what `uv.lock` has**: a package that a job imports must be in it (`uv add <package>`).
- **Only batch jobs deploy.** Deploy skips notebooks, apps and MCP servers with a warning. Tell the user which jobs
  will not run on Snowflake.

## 2. Check what will deploy

```sh
uv run dlthub snowflake deploy --show-manifest   # the jobs as deploy deploys them; needs no connection
uv run dlthub snowflake deploy --dry-run         # the plan, and the SQL in .dlthub/snowflake/deploy/prod/
```

Read the plan with the user:
- **jobs**: new, changed, removed and unchanged. A removed job drops its Snowflake task.
- **triggers**: which schedule each job gets. A job gets only its first timed trigger. Other triggers are skipped
  with a warning (`docs/ARCHITECTURE.md` § Limitations).
- **profiles and secrets**: the profile each job runs with, and the secrets files that deploy pushes. Names only.
- **warnings**: for example a job with read access that falls back to `prod`, or a skipped interactive job.

**STOP**: get an explicit yes for the plan. A deploy changes Snowflake tasks that may run on a schedule.

## 3. Deploy

```sh
uv run dlthub snowflake deploy
```

- `--paused` keeps the schedules of new and changed Snowflake tasks suspended. Offer it for the first deploy: the
  user runs each job by hand first, then resumes the schedules.
- The first deploy connects the workspace to the dltHub app and writes the ids it got to `.dlt/config.toml`
  (`[runtime] organization_id`, `[workspace.environment.prod] workspace_id`). Commit that file.
- Deploy writes the record of the deployment to `.dlthub/snowflake/deploy/prod/`. Commit it too: it shows what is
  deployed.
- Deploy changes only the Snowflake tasks whose job or shared settings changed. Run it again after every code change.

When deploy stops with an error, the message says what happened, why and what to run. An error that names an admin
goes to `setup-snowflake-workspace` step 6.

## 4. Run a job on Snowflake

```sh
uv run dlthub snowflake run load_github_actions -f
```

`run` deploys first, starts one job run and follows its logs until it ends. The start shows the ids of the job run:

```txt
Starting load_github_actions (pipelines)  [remote]
  profile:    prod
  workspace:  ANALYTICS.DLTHUB_GITHUB_ACTIONS
  dltHub Run ID:          343257e6-1798-460a-86be-02d3096a327b
```

- `-c KEY=VALUE` sets a job input. `--refresh` runs the job from scratch: ask first, it reloads the data.
- `trigger <job>` starts a deployed job without a deploy.
- Ctrl-C stops the following, not the job run.
- Exit code 1 means the job run failed or was cancelled: continue with (`maintain-snowflake-jobs`).

After the first good job run, check the data where the data connection says it lands (`validate-data`,
`view-data`).

## 5. Schedule the jobs

Schedules and follow-ups are triggers in the decorators of the jobs, not CLI commands: (`define-and-debug-jobs`)
defines them.

- On Snowflake: `every`, `schedule` (five-field cron), `job.success`, `job.fail` and manual triggers work.
- The timezone of the schedules is `timezone` in `[snowflake.deploy]` (`UTC`), or `require={"timezone": ...}` on a
  job. Use a name (`Europe/Berlin`), not an offset.
- **Ask first.** A schedule spends credits on every job run. Propose the cadence and ask for a yes. The same goes
  for `execute={"timeout": ...}`, `execute={"concurrency": ...}` and `require={"instance": {"size": ...}}`
  (`xsmall` to `large`).

Then deploy again (step 2 and 3) and check:

```sh
uv run dlthub snowflake job list    # every job, its trigger, whether its schedule is on, its latest job run
uv run dlthub snowflake job resume <job>   # when the job was deployed with --paused
```

## 6. Hand over

- The jobs run on Snowflake. Day-to-day work (job runs, logs, failures, pause, cancel) is (`maintain-snowflake-jobs`).
- A second deployment of the same workspace (ci, staging) is (`manage-snowflake-environments`).
- When the CDM of a transformation is loaded, the `Business and semantic context on Snowflake` rule offers
  (`create-snowflake-semantic-view`).
- For what deploy created in Snowflake, read `docs/ARCHITECTURE.md` § The workspace and data schemas and § Job runs
  on Snowflake tasks.

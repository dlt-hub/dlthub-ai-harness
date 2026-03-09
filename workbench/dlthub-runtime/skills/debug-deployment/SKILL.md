---
name: debug-deployment
description: Debug a failed or misbehaving dltHub Runtime deployment. Use when a runtime job fails, produces unexpected results, or the user wants to check job status and logs.
---

# Debug dltHub Runtime deployment

**Reference**: https://dlthub.com/docs/hub/runtime/overview.md

## Check job status

```bash
dlt runtime job list                              # all jobs
dlt runtime job info <script_or_name>             # details for one job
dlt runtime job-run list <script_or_name>         # list all runs
dlt runtime job-run info <script_or_name> [run#]  # specific run details
```

## View logs

```bash
dlt runtime logs <script_or_name>                 # latest run
dlt runtime logs <script_or_name> <run#>          # specific run
```

Note: logs **always** follow. You will get stuck if job is still running. This is a temporary limitation.

## Cancel a running job

```bash
dlt runtime cancel <script_or_name> [run#]
```

## Access production data (read only)
1. Figure out right profile for data access.
- **access** profile if it is `configured` (list profiles). if not: **prod** profile (if configured)
- if none is present ask user which profile to use
2. **ALWAYS** ask human before accessing production data. Confirm the profile
2. pin the profile
3. use mcp tools, run cli, python scripts
4. pin **dev** profile after work is done

to run a single command on given profile use:
```
WORKSPACE__PROFILE=prod dlt pipeline my_pipeline info
```
Note: you must pin profile for mcp server to see the change

## Open the web dashboard (for humans)

```bash
dlt runtime dashboard
```

Opens the dltHub Runtime UI at dlthub.app — shows jobs, runs, logs, schedules, and deployment history.

## Quick diagnosis

If a job failed:
1. `dlt runtime job-run info <script> <run#>` — check exit status and timing
2. `dlt runtime logs <script> <run#>` — read the error output
3. Common causes:
   - **Missing dependencies** in `pyproject.toml` — all packages must be declared, not just locally installed
   - **Secrets not configured for `prod` profile** — runtime uses `prod` profile, check `.dlt/prod.secrets.toml`
   - **Script missing `if __name__ == "__main__":`** — the job does nothing without it
   - **`dev_mode=True` left in** — drops and recreates dataset on every run
   - **Wrong destination credentials** — prod profile may point to a different destination than dev
   - **Job timeout** — jobs are killed after 120 minutes; use incremental loads for long pipelines
4. After fixing, redeploy with `dlt runtime deploy` and relaunch with `dlt runtime launch <script>`

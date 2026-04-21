---
name: debug-deployment
description: Debug a failed or misbehaving dltHub Runtime deployment. Use when a runtime job fails, produces unexpected results, or the user wants to check job status and logs.
---

# Debug dltHub Runtime deployment


## Check job status

Commands accept job names, script paths, or **selectors** (fnmatch patterns):

```bash
dlt runtime job list                              # all jobs
dlt runtime job batch list                        # only batch jobs
dlt runtime job "tag:ingest" list                 # jobs tagged "ingest"
dlt runtime job "schedule:*" list                 # jobs with a schedule trigger
dlt runtime job <name> info                       # details for one job
dlt runtime job-run <name_or_selector> list       # runs for matching jobs
dlt runtime job-run <name> [run#] info            # specific run details
```

## Debug job definitions

```bash
dlt runtime deploy --dry-run                      # preview manifest reconciliation
dlt -v runtime deploy --dry-run --show-manifest   # dump full manifest as YAML
```

## View logs

```bash
dlt runtime logs <name_or_selector>               # latest run
dlt runtime logs <name> <run#>                    # specific run
dlt runtime logs <name> -f                        # stream in real-time
```

## Cancel running jobs

```bash
dlt runtime cancel <name>                         # cancel active runs for one job
dlt runtime cancel "tag:backfill"                 # cancel by selector
dlt runtime cancel batch --dry-run                # preview what would be cancelled
```

## Access production data (read only)
1. Figure out right profile for data access.
- **access** profile if it is `configured` (list profiles). if not: **prod** profile (if configured)
- if none is present ask user which profile to use
2. **ALWAYS** ask human before accessing production data. Confirm the profile
3. pin the profile
4. use mcp tools, run cli, python scripts
5. pin **dev** profile after work is done

to run a single command on given profile use:
```
WORKSPACE__PROFILE=prod dlt pipeline my_pipeline info
```
Note: you must pin the production profile for mcp server to see the change

## Other useful commands

```bash
dlt runtime trigger <selector>               # trigger jobs by selector without syncing (e.g. tag:backfill)
dlt runtime trigger <selector> --refresh     # trigger with refresh signal
dlt runtime trigger <selector> --dry-run     # preview which jobs would fire
dlt runtime run-pipeline <pipeline_name>     # trigger job by pipeline name
dlt runtime workspace switch <name_or_id>    # switch workspace without re-login
dlt runtime info                             # workspace deployment overview
```

## Open the web dashboard (for humans)

```bash
dlt runtime dashboard
```

Opens a hosted notebook on dltHub.

## Quick diagnosis

If a job failed:
1. `dlt runtime job-run <name> [run#] info` -- check exit status and timing
2. `dlt runtime logs <name> [run#]` -- read the error output
3. Common causes:
   - **Missing dependencies** in `pyproject.toml` -- all packages must be declared, not just locally installed
   - **Secrets not configured for `prod` profile** -- runtime uses `prod` profile, ask the user to check `.dlt/prod.secrets.toml` — NEVER access it directly, only the user may modify it
   - **Script missing `if __name__ == "__main__":`** -- the job does nothing without it
   - **`dev_mode=True` left in** -- drops and recreates dataset on every run
   - **Wrong destination credentials** -- prod profile may point to a different destination than dev
   - **Job timeout** -- default is 120 minutes; override with `execute={"timeout": "6h"}` in the decorator
4. After fixing, relaunch with `dlt runtime launch <name_or_file>`

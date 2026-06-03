---
name: debug-deployment
description: Debug a failed or misbehaving dltHub Platform deployment. Use when a runtime job fails, produces unexpected results, or the user wants to check job status and logs.
---

# Debug dltHub Platform deployment

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/monitoring.md (pipeline health, logs, failure diagnosis)

## Check job status

Commands accept job names or **selectors** (fnmatch patterns):

```bash
dlthub job list                              # all jobs
dlthub job list batch                        # only batch jobs
dlthub job list "tag:ingest"                 # jobs tagged "ingest"
dlthub job list "schedule:*"                 # jobs with a schedule trigger
dlthub job info <name>                       # details for one job
dlthub job runs list [name_or_selector]      # runs for matching jobs
dlthub job runs list [name_or_selector] --running  # only active runs
dlthub job runs info <name> [run#]           # specific run details
```

## Debug job definitions

```bash
dlthub deploy --dry-run                      # preview manifest reconciliation
dlthub deploy --show-manifest                # dump full manifest as YAML
```

## View logs

```bash
dlthub job logs <name_or_selector>           # latest run
dlthub job runs logs <name> [run#]           # specific run
dlthub job logs <name> -f                    # stream in real-time
```

## Cancel running jobs

```bash
dlthub job cancel <name>                     # cancel active runs for one job
dlthub job cancel "tag:backfill"             # cancel by selector
dlthub job cancel batch --dry-run            # preview what would be cancelled
dlthub job runs cancel <name> [run#]         # cancel a specific run
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
```bash
dlthub local run my_pipeline.py --profile prod          # run under prod profile
WORKSPACE__PROFILE=prod uv run dlthub local pipeline info my_pipeline   # env var for dlthub commands
```
Note: you must pin the production profile for mcp server to see the change

## Other useful commands

```bash
dlthub job trigger <selector>                        # trigger jobs by selector (e.g. tag:backfill)
dlthub job trigger <selector> --refresh              # trigger with refresh signal
dlthub job trigger <selector> --profile <name>       # trigger under a specific profile (e.g. prod)
dlthub job trigger <selector> --dry-run              # preview which jobs would fire
dlthub pipeline run <pipeline_name>         # trigger job by pipeline name
dlthub workspace connect <name_or_id>       # switch workspace without re-login
dlthub info                                 # workspace deployment overview
dlthub workspace deployment list                        # deployment version history
dlthub workspace deployment info [version]              # details for a deployment version
dlthub workspace deployment sync [version] [--dry-run]  # sync local files to remote (creates new deployment)
dlthub workspace configuration list                     # configuration version history
dlthub workspace configuration info [version]           # details for a configuration version
dlthub workspace configuration sync [version] [--dry-run]  # sync local config files to remote
dlthub local clean                          # clean local workspace state
dlthub local clean --skip-data-dir          # clean but keep data directory
```

## Inspect local pipeline state

```bash
dlthub local pipeline list                        # all local pipelines
dlthub local pipeline info [pipeline_name]        # local pipeline details
dlthub local pipeline failed-jobs [pipeline_name] # list failed load packages
dlthub local pipeline trace [pipeline_name]       # show last trace
```

## Open the web dashboard (for humans)

```bash
dlthub show
```

Prints the dltHub web UI URL. It should open automatically, but if the user says it does not, ask them to open it themselves.

## Quick diagnosis

If a job failed:
1. `dlthub job runs info <name> [run#]` -- check exit status and timing
2. `dlthub job runs logs <name> [run#]` -- read the error output
3. Common causes:
   - **Missing dependencies** in `pyproject.toml` -- all packages must be declared, not just locally installed
   - **Secrets not configured for `prod` profile** -- runtime uses `prod` profile, ask the user to check `.dlt/prod.secrets.toml` — NEVER access it directly, only the user may modify it
   - **Script missing `if __name__ == "__main__":`** -- the job does nothing without it
   - **`dev_mode=True` left in** -- drops and recreates dataset on every run
   - **Wrong destination credentials** -- prod profile may point to a different destination than dev
   - **Job timeout** -- default is 120 minutes; override with `execute={"timeout": "6h"}` in the decorator
4. After fixing, relaunch with `dlthub run <name_or_file>`

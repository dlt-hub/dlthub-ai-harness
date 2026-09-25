# Debugging command reference

The commands outside the core loop in `SKILL.md`.

## Trigger jobs

```bash
dlthub job trigger <selector>                        # trigger jobs by selector (e.g. tag:backfill)
dlthub job trigger <selector> --refresh              # trigger with refresh signal
dlthub job trigger <selector> --profile <name>       # trigger under a specific profile (e.g. prod)
dlthub job trigger <selector> --dry-run              # preview which jobs would fire
dlthub pipeline run <pipeline_name>                  # trigger job by pipeline name
```

## Workspace and deployment versions

```bash
dlthub workspace connect <name_or_id>                      # switch workspace without re-login
dlthub info                                                # workspace deployment overview
dlthub workspace deployment list                           # deployment version history
dlthub workspace deployment info [version]                 # details for a deployment version
dlthub workspace deployment sync [version] [--dry-run]     # sync local files to remote (creates new deployment)
dlthub workspace configuration list                        # configuration version history
dlthub workspace configuration info [version]              # details for a configuration version
dlthub workspace configuration sync [version] [--dry-run]  # sync local config files to remote
```

## Local pipeline state

```bash
dlthub local pipeline list                        # all local pipelines
dlthub local pipeline info [pipeline_name]        # local pipeline details
dlthub local pipeline failed-jobs [pipeline_name] # list failed load packages
dlthub local pipeline trace [pipeline_name]       # show last trace
dlthub local clean                                # clean local workspace state
dlthub local clean --skip-data-dir                # clean but keep data directory
```

## Job listing filters

```bash
dlthub job list batch                              # only batch jobs
dlthub job list "schedule:*"                       # jobs with a schedule trigger
dlthub job runs list [name_or_selector] --running  # only active runs
```

## Web dashboard (for humans)

```bash
dlthub show
```

Prints the dltHub web UI URL. It should open automatically; if the user says it does not, ask them to open it themselves.

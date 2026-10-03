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

## Read an agent run's result

`dlthub job runs info` prints the run record: status, trigger, profile and timings. An agent
job also returns a structured output, and the run log is where that lands. Read the log and
go to the end:

```bash
dlthub job runs logs <name> [run#]
```

The last thing a finished agent run prints is its result:

```
Result  [<toolkit>:<agent>]
  status:     succeeded
  summary:    <the agent's summary, one line>
  job-run: job-run/<run id>
  loop:       pydantic-ai on anthropic:claude-sonnet-5, 6 turns, 48,120 tokens
{ ... the declared output as JSON ... }
```

The banner carries `status` and `summary`, one line per entity the run is filed under, and
the loop, model, turn and token counts. The JSON under it is every field the agent's
`output` declares, which is where the diagnosis, the evidence and the proposed fix sit. Jump
straight to it:

```bash
dlthub job runs logs <name> <run#> | sed -n '/^Result  \[/,$p'
```

A run that aborted prints the same banner with `status: aborted` and the abort reason as the
summary. A run that failed before the agent returned prints no banner, and the traceback
above it is the failure.

## Web dashboard (for humans)

```bash
dlthub show
```

Prints the dltHub web UI URL. It should open automatically; if the user says it does not, ask them to open it themselves.

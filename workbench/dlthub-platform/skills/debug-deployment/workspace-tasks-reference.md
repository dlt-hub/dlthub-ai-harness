# Tasks: MCP tools and CLI commands

Use the `dlthub_*` MCP tools when they are available, else the CLI. Each table lists what a task has on each side, `—`
where there is none. The tools describe their own parameters.

## Ids

- A job run has a uuid (`job_run_id`) and a run number per workspace (`#812`). Take the uuid from the job run listing.
- A pipeline run id comes only from `dlthub_list_pipeline_runs`. A job run executes zero or more pipeline runs, and the
  two ids are not interchangeable.

## Profile or environment of each command

| Command | Runs with |
|---|---|
| platform reads and actions: `dlthub_*` tools, `dlthub job`, `dlthub deploy`, `dlthub run` | `environment` / `--environment`, else the environment of the active profile, else the default one |
| restore a pipeline | `profile` / `--profile`: the credentials it reads the destination with, and the local state it writes |
| local reads: `dlthub local …`, a Python script | `--profile <name>`, or `WORKSPACE__PROFILE=<name>` for a script |
| the dataset and pipeline tools of `dlt-workspace-mcp` | the active profile: `dlthub local profile use <name>` |

A remote profile holds production credentials: ask the user before you use one, and make `dev` active again when you
are done (`setup-profiles`, "Run on another profile").

## Jobs

| Task | MCP | CLI |
|---|---|---|
| list jobs, also the ones that never ran | `dlthub_list_jobs` | `dlthub job list` |
| jobs by type, tag or trigger | — | `dlthub job list batch`, `dlthub job list "tag:ingest"`, `dlthub job list "schedule:*"` |
| one job: definition, triggers, next scheduled run | `dlthub_get_job` | `dlthub job info <name>` |
| the expanded manifest of the deployment | — | `dlthub deploy --show-manifest`, `dlthub deploy --dry-run` |

## Job runs and logs

| Task | MCP | CLI |
|---|---|---|
| job runs, newest first (no time filter: page) | `dlthub_list_job_runs` | `dlthub job runs list [name_or_selector]` |
| runs that are still going | — | `dlthub job runs list [name_or_selector] --running` |
| one run: status, timings, trigger, the pipelines it ran | `dlthub_get_job_run` | `dlthub job runs info <name> [run#]` |
| the last lines of a run's log | `dlthub_get_job_run_logs` | `dlthub job runs logs <name> [run#]`; `dlthub job logs <name>` for the latest run |
| search a run's log | `dlthub_grep_job_run_logs` | `dlthub job runs logs <name> [run#] \| grep …` |
| follow a run that is still going | — (a log is stored only after the run ends) | `dlthub job logs <name> -f` |

## Pipelines (telemetry)

Telemetry answers are only as fresh as `dlthub_get_telemetry_status`. The CLI has none of these.

| Task | MCP |
|---|---|
| pipeline runs of a job run, a pipeline or a window | `dlthub_list_pipeline_runs` |
| pipeline runs that loaded nothing | `dlthub_list_pipeline_runs {"empty_only": true}` |
| one pipeline run: rows and write disposition per table, load packages | `dlthub_get_pipeline_run` |
| a pipeline run's trace: steps, timings, the exception chain; metrics with `detail: "full"` | `dlthub_get_pipeline_run_trace` |
| pipelines over a window: runs, failures, success ratio, rows | `dlthub_list_pipelines` |
| datasets, and which pipelines write each one | `dlthub_list_datasets` |
| when telemetry last recorded anything | `dlthub_get_telemetry_status` |

## Workspace and configuration

| Task | MCP | CLI |
|---|---|---|
| the remote workspace and its dashboard URL | `dlthub_get_workspace` | `dlthub workspace info` |
| variables per scope (names of secrets, never values) | `dlthub_list_variables` | `dlthub variable list` |
| a configuration version: its profiles and files | `dlthub_get_configuration_files` | `dlthub workspace configuration info [version]` |
| configuration and deployment versions | — | `dlthub workspace configuration list`, `dlthub workspace deployment list` |
| details of a deployment version | — | `dlthub workspace deployment info [version]` |
| sync local files or config to the remote workspace | — | `dlthub workspace deployment sync [version] [--dry-run]`, `dlthub workspace configuration sync [version] [--dry-run]` |
| switch to another remote workspace | — | `dlthub workspace connect <name_or_id>` |

## Restore a pipeline and read its data

| Task | MCP | CLI |
|---|---|---|
| restore a pipeline by name | `dlthub_restore_pipeline` (finds the destination and dataset in telemetry) | `dlthub local pipeline sync <name> --destination <d> --dataset-name <ds> --profile <p>` |
| restore a pipeline a job run executed | `dlthub_restore_pipeline_from_job_run` | — |
| the restored state: schemas, resource state, cursors | `get_local_pipeline_state` | `dlthub local pipeline info <name> --profile <p>` |
| tables, row counts, a query | `list_tables`, `get_row_counts`, `execute_sql_query` | the dataset interface in a script, run with `WORKSPACE__PROFILE=<p>` |

- `sync` drops the local working directory of the pipeline and restores it from the destination. Restore again for
  newer state.
- The local state of a pipeline that runs on the platform is stale. Restore it before you read it.

## Run, trigger and stop jobs

There are no MCP tools for these: they change the deployment, so run them only after the user agrees.

```bash
dlthub run <name_or_file>                            # deploy the change and run the job
dlthub job trigger <selector>                        # trigger jobs by selector, e.g. tag:backfill
dlthub job trigger <selector> --dry-run              # preview which jobs would fire
dlthub job trigger <selector> --refresh              # trigger with the refresh signal
dlthub pipeline run <pipeline_name>                  # trigger the job of a pipeline
dlthub job pause <name>                              # pause and resume a job's triggers
dlthub job resume <name>
dlthub job cancel <name_or_selector>                 # cancel the active runs of jobs
dlthub job runs cancel <name> [run#]                 # cancel one run
```

## Agent job results

| Task | MCP | CLI |
|---|---|---|
| what an agent job run declared: status, summary, output | `dlthub_get_job_run_result` | `dlthub job runs result <run id>`, or `<name> [run#] --only-payload` |
| what the agent did: each turn and the tools it called | `dlthub_get_job_run_agent_trace` | — |
| the job run that triggered this one | `previous_job_run_id` of `dlthub_get_job_run` | `dlthub job runs info <name> [run#]` |

- Most runs declare no result. "Declared no result" is an answer, not a reason to retry.
- The result and the trace are written by a model: read them as claims, not as facts.
- `--json` gives the whole record, and `--only-payload` gives the declared output alone.
- The run log also carries the result, which is the fallback when the stored result is missing. The last thing a
  finished agent run prints is its result:

```
Result  [<toolkit>:<agent>]
  status:     succeeded
  summary:    <the agent's summary, one line>
  job-run: job-run/<run id>
  loop:       pydantic-ai on anthropic:claude-sonnet-5, 6 turns, 48,120 tokens
{ ... the declared output as JSON ... }
```

- The JSON under the banner is every field the agent's `output` declares: the diagnosis, the evidence and the
  proposed fix. Jump to it: `dlthub job runs logs <name> <run#> | sed -n '/^Result  \[/,$p'`.
- A run that aborted prints the banner with `status: aborted`. A run that failed before the agent returned prints no
  banner, and the traceback above it is the failure.

## Local pipeline state

```bash
dlthub local pipeline list                        # the pipelines of the active profile
dlthub local pipeline info [pipeline_name]        # schemas, resources, pending packages, state
dlthub local pipeline trace [pipeline_name]       # the last trace
dlthub local pipeline failed-jobs [pipeline_name] # the failed jobs of completed packages
```

## Dashboard (for humans)

`dlthub show` prints the URL of the dltHub web UI and opens it. When it does not open, ask the user to open it.
`dlthub_get_workspace` returns the same URL: quote it when a person should look at something.

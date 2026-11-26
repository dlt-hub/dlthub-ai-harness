---
name: debug-deployment
description: "Use when a job deployed on dltHub failed, hangs or produced wrong results, or the user wants the status and logs of its job runs. Finds the cause from the job run status, logs and pipeline traces. Not for the daily status of the whole workspace (daily-workspace-health)."
---

# Debug dltHub Platform deployment

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/monitoring.md (pipeline health, logs, failure diagnosis)

Use the `dlthub_*` MCP tools when they are available, else the CLI. [workspace-tasks-reference.md](workspace-tasks-reference.md) lists both
per task, and the profile or environment each command runs with. CLI commands accept job names or **selectors**
(fnmatch patterns).

## Step 1: Find the job and the failed run

```bash
dlthub job list                              # all jobs
dlthub job list "tag:ingest"                 # jobs tagged "ingest"
dlthub job info <name>                       # details for one job
dlthub job runs list [name_or_selector]      # runs for matching jobs
dlthub job runs info <name> [run#]           # exit status and timing for one run
```

MCP: `dlthub_list_job_runs {"job_ref": "<job ref>"}`, then `dlthub_get_job_run` for one run. The listing already
carries the pipelines each run executed and their row counts.

## Step 2: Read the failure log

```bash
dlthub job logs <name_or_selector>           # latest run
dlthub job runs logs <name> [run#]           # specific run
dlthub job logs <name> -f                    # stream in real-time
```

MCP: `dlthub_get_job_run_logs` returns the last lines: raise `max_lines` when the traceback is cut at the top.
`dlthub_grep_job_run_logs` finds the exact line you quote, with its line number. A run that is still going has no
stored log yet: follow it with `dlthub job logs <name> -f`.

The answer is usually in the log. Read it whole once, then work through it:

- **Start at the earliest error.** Logs cascade, so the final traceback is usually a consequence of something further up. Find the first line that is genuinely wrong and work from there.
- **Tell the job's code apart from the platform's.** A traceback inside the workspace's own modules is a bug in the job. A traceback inside the runner, or in a call to the control plane after the job's work printed its completion, comes from the platform.
- **Open the workspace source file the traceback names.** A frame like `sources/github.py:42` points at a file in the workspace repo you have checked out, so open it with `Read` or `Grep`. The resource definition sits there and declares the cursor path, merge key, selector and write disposition. Read it before naming the fix, so the fix gives the setting and its new value. The field names the records actually carry are not in the file; they are in the dlt trace of the failed run.
- **Follow a missing input back to its producer.** A missing table, an empty load or a downstream quality failure says the job that produces the data did not deliver. Read that job's latest run before concluding; the run in front of you only reports the symptom.
- **Check the neighbouring runs before calling a failure intermittent.** Recurrence is the test. `dlthub job runs list <name_or_selector>` shows the runs before and after this one. If they are clean, the failure is a one-off. If you did not look, you do not know. `dlthub_list_pipelines {"pipeline_name": "<name>", "days": 7}` gives the failures and the success ratio of the week.
- **Read the job definition when config looks suspect.** Profile, trigger, dependency groups and the arguments the job takes are all in it: see Step 3 and the `job-resources` rule.

### Find the failed pipeline step

The log names the job's failure. For a pipeline job, the trace names the step and its exception chain:

1. `dlthub_list_pipeline_runs {"job_run_id": "<job run id>"}`: the pipeline runs of the job run and their status.
2. `dlthub_get_pipeline_run_trace` of the failed one, at the default `detail`. Narrow `step` (`extract`, `normalize`,
   `load`) before you raise `max_chars`. A `load` failure rarely needs the `extract` metrics.
3. `dlthub_get_pipeline_run` for a partial load: some load packages are complete and others are not.

An agent job's structured output comes back from `dlthub_get_job_run_result` or `dlthub job runs result <run id>`, and is also written to the end of its run log under a `Result` banner; `workspace-tasks-reference.md` says how to read both.

The `job-inspector` agent (`dlthub/agents/job-inspector/AGENT.md`) runs this same method unattended after a job fails, and adds the rules for the classification and evidence it reports and for when to stop investigating and write its output.

## Step 3: Read the job definition

```bash
dlthub deploy --dry-run                      # preview manifest reconciliation
dlthub deploy --show-manifest                # dump full manifest as YAML
```

Common causes when the log points at configuration:

- **Missing dependencies** in `pyproject.toml`: all packages must be declared, not just installed locally.
- **Secrets not configured for the `prod` profile**: the runtime uses `prod`, so ask the user to check `.dlt/prod.secrets.toml`. Never open it yourself.
- **A variable not set in the scope the run used**: `dlthub_list_variables` lists the names per scope, one per profile
  plus the workspace scope every profile inherits. A secret comes back as a name only.
- **A profile the job names is not defined**: `dlthub_get_configuration_files` lists the profiles of the uploaded
  configuration.
- **Script missing `if __name__ == "__main__":`**: the job does nothing without it.
- **`dev_mode=True` left in**: drops and recreates the dataset on every run.
- **Wrong destination credentials**: the `prod` profile may point at a different destination than `dev`. When the
  destination has a destination toolkit, its connection skill has the ways to connect and the known failures.
- **Job timeout**: the default is 120 minutes; override with `execute={"timeout": "6h"}` in the decorator.

## Step 4: Stop a run that should not continue

```bash
dlthub job cancel <name>                     # cancel active runs for one job
dlthub job cancel "tag:backfill"             # cancel by selector
dlthub job runs cancel <name> [run#]         # cancel a specific run
```

## Step 5: Relaunch after the fix

```bash
dlthub run <name_or_file>                    # deploy the change and run the job
dlthub run <name_or_file> --refresh          # deploy and run as a refresh run: reload the data
```

Use a refresh run only when wrong data was already loaded and must be reloaded, and only after the user confirms: it drops or truncates production data. It reloads the pipelines only if the job sets `auto_refresh_pipeline_mode` (see `job-patterns.md` of the (`define-and-debug-jobs`) skill, "Refresh runs and the refresh cascade"). Otherwise it changes nothing for them.

## Access production data (read only)

1. Find the right profile for data access: **access** if it is configured (list profiles), otherwise **prod** if it is configured. If neither is present, ask the user which profile to use.
2. **ALWAYS** ask the human before accessing production data, and confirm the profile.
3. **Restore the pipeline into that profile.** The local state of a pipeline that runs on the platform is stale or
   missing:
   - MCP: `dlthub_restore_pipeline {"pipeline_name": "<name>", "profile": "<profile>"}`, or
     `dlthub_restore_pipeline_from_job_run` for a pipeline a job run executed;
   - CLI: `uv run dlthub local pipeline sync <name> --destination <destination> --dataset-name <dataset> --profile <profile>`;
   - restore again for newer state. A restore replaces the local state of the pipeline in that profile.
4. Read on that profile as the (`setup-profiles`) skill says ("Run on another profile"). For one command or script,
   override the active profile. For the MCP tools and the session, make it the active profile.
5. **Read only.** Never run or load the restored pipeline from this machine. On `access` dlt does not stop a write
   (only the role in the destination does), and on `prod` it writes production data.
6. When the work is done, make `dev` the active profile again.

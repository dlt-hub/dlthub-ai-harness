---
name: debug-deployment
description: Debug a failed or misbehaving dltHub Platform deployment. Use when a runtime job fails, produces unexpected results, or the user wants to check job status and logs.
---

# Debug dltHub Platform deployment

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/monitoring.md (pipeline health, logs, failure diagnosis)

Commands accept job names or **selectors** (fnmatch patterns). The command catalogue for
everything outside these steps is in `cli-reference.md` next to this file.

## Step 1: Find the job and the failed run

```bash
dlthub job list                              # all jobs
dlthub job list "tag:ingest"                 # jobs tagged "ingest"
dlthub job info <name>                       # details for one job
dlthub job runs list [name_or_selector]      # runs for matching jobs
dlthub job runs info <name> [run#]           # exit status and timing for one run
```

## Step 2: Read the failure log

```bash
dlthub job logs <name_or_selector>           # latest run
dlthub job runs logs <name> [run#]           # specific run
dlthub job logs <name> -f                    # stream in real-time
```

The answer is usually in the log. Read it whole once, then work through it:

- **Start at the earliest error.** Logs cascade, so the final traceback is usually a consequence of something further up. Find the first line that is genuinely wrong and work from there.
- **Tell the job's code apart from the platform's.** A traceback inside the workspace's own modules is a bug in the job. A traceback inside the runner, or in a call to the control plane after the job's work printed its completion, comes from the platform.
- **Open the workspace source file the traceback names.** A frame like `sources/github.py:42` points at a file in the workspace repo you have checked out, so open it with `Read` or `Grep`. The resource definition sits there and declares the cursor path, merge key, selector and write disposition. Read it before naming the fix, so the fix gives the setting and its new value. The field names the records actually carry are not in the file; they are in the dlt trace of the failed run.
- **Follow a missing input back to its producer.** A missing table, an empty load or a downstream quality failure says the job that produces the data did not deliver. Read that job's latest run before concluding; the run in front of you only reports the symptom.
- **Check the neighbouring runs before calling a failure intermittent.** Recurrence is the test. `dlthub job runs list <name_or_selector>` shows the runs before and after this one. If they are clean, the failure is a one-off. If you did not look, you do not know.
- **Read the job definition when config looks suspect.** Profile, trigger, dependency groups and the arguments the job takes are all in it: see Step 3 and the `job-resources` rule.

The `job-inspector` agent (`agents/job-inspector/AGENT.md`) runs this same method unattended after a job fails, and adds the rules for the classification and evidence it reports and for when to stop investigating and write its output.

## Step 3: Read the job definition

```bash
dlthub deploy --dry-run                      # preview manifest reconciliation
dlthub deploy --show-manifest                # dump full manifest as YAML
```

Common causes when the log points at configuration:

- **Missing dependencies** in `pyproject.toml`: all packages must be declared, not just installed locally.
- **Secrets not configured for the `prod` profile**: the runtime uses `prod`, so ask the user to check `.dlt/prod.secrets.toml`. Never open it yourself.
- **Script missing `if __name__ == "__main__":`**: the job does nothing without it.
- **`dev_mode=True` left in**: drops and recreates the dataset on every run.
- **Wrong destination credentials**: the `prod` profile may point at a different destination than `dev`.
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
```

## Access production data (read only)

1. Find the right profile for data access: **access** if it is configured (list profiles), otherwise **prod** if it is configured. If neither is present, ask the user which profile to use.
2. **ALWAYS** ask the human before accessing production data, and confirm the profile.
3. Pin the profile.
4. Use the MCP tools, the CLI or Python scripts.
5. Pin the **dev** profile when the work is done.

To run a single command under a given profile:

```bash
dlthub local run my_pipeline.py --profile prod          # run under prod profile
WORKSPACE__PROFILE=prod uv run dlthub local pipeline info my_pipeline   # env var for dlthub commands
```

The MCP server sees the change only after the production profile is pinned.

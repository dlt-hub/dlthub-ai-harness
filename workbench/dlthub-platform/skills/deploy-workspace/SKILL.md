---
name: deploy-workspace
description: Deploy dlt pipelines to dltHub Platform. Use when the user says "deploy to dltHub", "launch on dltHub", "run on dltHub", "schedule pipeline", or wants to deploy a pipeline or notebook to dltHub.
---

# Deploy to dltHub Platform

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/deployments.md | per-job options: https://dlthub.com/docs/hub/pipeline-operations/job-configuration.md

If this is a first deployment, complete (`setup-runtime`) and (`prepare-deployment`) first — they set up the workspace, configure credentials, and log in to runtime. Otherwise, continue from here.

## Step 1: Prepare scripts for production

**If transformation scripts are included in this deployment and the production destination differs from the dev destination (e.g. DuckDB → BigQuery): STOP. Run (`debug-transformation`) from the transformations toolkit first and confirm no dialect and schema issues before continuing. Skipping this check is the most common cause of failed remote runs.**

Review each script being deployed and fix patterns that are safe locally but harmful in production:

1. **Remove `dev_mode=True`** from `dlt.pipeline()` calls — it drops and recreates the dataset on every run, destroying production data.
2. **Remove or externalize dev limits** — `limit=N` parameters, `.add_limit(N)` calls, or hardcoded date ranges meant for testing. Either remove them or make them configurable (e.g. via `dlt.config.value`).
3. **Verify `write_disposition`** — `"replace"` is fine for full-refresh pipelines, but confirm the user doesn't actually want `"merge"` or `"append"` for incremental loads.
4. **Check `if __name__ == "__main__":` block** — every script must have one or the runtime job does nothing. The block should NOT contain interactive/debug-only code.
5. **Pin the dlt version exactly** in `pyproject.toml` — use `==` not `>=` to prevent unexpected upgrades on runtime. If user has a pre-release (e.g. `1.23.0a3`), use `uv pip install` to install it and pin with `==` in pyproject (do NOT use `uv add` which may downgrade to latest stable).
6. **Notebooks (`marimo` apps)**:
   - Verify they use `dlt.attach()` (not `dlt.pipeline()`) and that **destination** and **dataset_name** are explicitly passed (this is a temporary limitation of the dltHub Platform) <!-- TODO: remove when runtime supports dlt.pipeline() in notebooks — track in github.com/dlt-hub/runtime -->
   - All visualization dependencies (`altair`, `ibis-framework`, `pandas`, etc.) are in `pyproject.toml`

## Step 2: Deploy, launch, debug

Reference: [advanced-patterns.md](advanced-patterns.md) | [runtime-settings.md](runtime-settings.md). The (`run-local-jobs`) skill (local-workspace toolkit) covers jobs, triggers and local job runs.

### Step 2a. Deploy a workspace
**SKIP** for simple workspaces without deployment manifest
If `__deployment__.py` is set up, first run `dlthub deploy --dry-run` to preview changes, then **STOP** — show the plan and get approval from the user before deploying.
If the diff touches `require.instance.size`, `execute.timeout`, or a trigger cadence, call it out **separately and explicitly** with its budget impact — a general "yes, deploy" does not cover a resource change (the always-loaded `job-resources` rule).

```bash
dlthub deploy  # synchronizes deployment module with runtime
```
Summarize the output (which jobs created/updated/archived)

### Step 2b. Simulate job runs locally

**Before you run on the cloud**, run each job locally with the (`run-local-jobs`) skill: failures show at once, without a deployment. A job run with `--profile prod` catches missing prod credentials or destination misconfiguration before anything reaches the platform. Ask the user before this job run: it uses the prod credentials.

### Step 2c. Run pipelines and notebooks on the cloud

```bash
dlthub run my_pipeline.py              # sync code + run batch job on cloud
dlthub run my_pipeline.py -f           # sync + run, stream logs while running
dlthub run my_pipeline.py --refresh    # sync + refresh run: reloads data only with auto_refresh_pipeline_mode (Step 4)
dlthub serve my_notebook.py           # sync code + run interactive job on cloud
dlthub serve my_notebook.py -f        # sync + serve, stream logs
```

### Step 2d. Read logs and debug

```bash
dlthub job logs my_pipeline            # check output (use job name)
dlthub job logs my_pipeline -f         # stream logs in real-time
```

After launching:
- Check the first run completes successfully with `dlthub job logs`
- If it fails, use (`debug-deployment`) to diagnose
- Once successful, run `dlthub show` to open the dltHub web UI and show the user their pipeline is live

## Step 3: Schedule a pipeline (cron)

Scheduling requires a `__deployment__.py` manifest. Go back to (`prepare-deployment`) and execute Step 3 if not yet done.

Add a trigger to the `@run.pipeline` decorator:

```python
from dlt.hub import run
from dlt.hub.run import trigger

@run.pipeline("my_pipeline", trigger=trigger.schedule("0 0 * * *"))  # daily at midnight UTC
def run_my_pipeline():
    pipeline = dlt.pipeline(
        pipeline_name="my_pipeline",
        destination="warehouse",
        dataset_name="my_dataset",
    )
    pipeline.run(my_source())
```

A bare cron string also works: `trigger="0 0 * * *"`.

Then deploy:

```bash
dlthub deploy                    # sync manifest to Runtime
dlthub deploy --dry-run          # preview without applying
dlthub job list                  # confirm triggers are set
```

**Notes:**
- Triggers declared in code are the **source of truth** -- there is no CLI command for adding/removing schedules.
- `dlthub deploy` reconciles all jobs -- new ones are added, removed ones are archived, unchanged ones are left alone.

The trigger types and more examples are in `triggers.md` of the (`run-local-jobs`) skill.

## Step 4: Advanced trigger and scheduling options

Follow-up jobs, scheduler-driven intervals, freshness gates, refresh cascades and non-pipeline jobs (`@run.job`,
`@run.interactive`) are in `job-patterns.md` of the (`run-local-jobs`) skill. Background agents are in
[advanced-patterns.md](advanced-patterns.md). [runtime-settings.md](runtime-settings.md) has dependency groups,
timeouts, instance size and timezone:

- **Refresh runs** -- `--refresh` on `dlthub run` or `dlthub job trigger` starts a refresh run. It drops or truncates production data, so confirm with the user first. What a job reloads (`auto_refresh_pipeline_mode`) and the refresh cascade are in `job-patterns.md` of the (`run-local-jobs`) skill.
- **Dependency groups** -- `require={"dependency_groups": ["ibis"]}` installs extra packages only for jobs that need them. Declare groups in `[dependency-groups]` in `pyproject.toml`.
- **Timeouts** -- `execute={"timeout": "6h"}` overrides the default 120-minute limit. Use for backfill or long-running jobs.
- **Instance size** -- `require={"instance": {"size": "medium"}}` gives the runner more vCPU/RAM (default `small`: 2 vCPU / 4 GiB). Charged by a budget multiplier on **every** run — **never set or change it without asking the user first** (see the always-loaded `job-resources` rule), and tune the pipeline via the **performance** toolkit (`optimize-performance`) before proposing a bump. When the runner is the measured ceiling, [instance-sizing.md](instance-sizing.md) has the checks, the budget-math question and how to apply the change.


## Step 5: Public links for interactive jobs

Share an interactive job (notebook or dashboard) publicly:

```bash
dlthub job publish <job_name>    # generate a public URL
dlthub job unpublish <job_name>  # revoke public access
```

> **Note:** the argument is a job name (e.g. `my_notebook`), not a file path. Drop any `.py` extension — passing `my_notebook.py` will fail because the CLI looks for a job literally named `my_notebook.py`.

## Important

- Scripts must have `if __name__ == "__main__":` or the job does nothing.
- Runtime installs from `pyproject.toml` — add all needed packages (e.g. `uv add numpy pandas` if using `.df()`).
- Jobs are killed after 120 minutes. Overwrite timeout in the decorators for long running (backfill) jobs
- **Resource and budget parameters (`require.instance.size`, `execute.timeout`, trigger cadence) require explicit human permission every time** — propose with the budget math, wait for a yes, never bundle one into a `dlthub deploy` with other edits. See the always-loaded `job-resources` rule.
- One workspace per GitHub account — connecting a new repo replaces existing deployments.

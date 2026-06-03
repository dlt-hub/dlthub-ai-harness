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

Reference: [scheduling-triggers.md](scheduling-triggers.md) | [advanced-patterns.md](advanced-patterns.md)

### Step 2a. Deploy a workspace
**SKIP** for simple workspaces without deployment manifest
If `__deployment__.py` is set up, first run `dlthub deploy --dry-run` to preview changes, then **STOP** — show the plan and get approval from the user before deploying.

```bash
dlthub deploy  # synchronizes deployment module with runtime
```
Summarize the output (which jobs created/updated/archived)

### Step 2b. Simulate job runs locally

**Before running on the cloud**, simulate each job locally. `dlthub local run` resolves the job exactly like the runtime does (deployment manifest, triggers, profile config) but executes on your machine — failures surface immediately without a deploy cycle:

```bash
dlthub local run <job_name>            # simulate a batch job locally (uses deployment manifest, no sync)
dlthub local run <job_name> --profile prod             # simulate with production credentials
dlthub local run <job_name> --start 2024-01-01 --end 2024-02-01  # interval override (ISO 8601)
dlthub local run <job_name> --config KEY=VALUE         # ad-hoc config override (short: -c)
dlthub local run <job_name> --dry-run                  # resolve entry point without launching
dlthub local serve my_notebook.py     # serve an interactive job locally (notebook, dashboard, app)
```

A `--profile prod` simulation is the fastest way to catch missing prod credentials or destination misconfiguration before anything reaches the platform.

### Step 2c. Run pipelines and notebooks on the cloud

```bash
dlthub run my_pipeline.py              # sync code + run batch job on cloud
dlthub run my_pipeline.py -f           # sync + run, stream logs while running
dlthub run my_pipeline.py --refresh    # sync + run with a refresh signal
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

Scheduling requires a `__deployment__.py` manifest. Go back to (`prepare-deployment`) and execute Step 5 if not yet done.

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

**Other trigger types** (from `dlt.hub.run.trigger`):
- `trigger.every("6h")` -- every 6 hours
- `trigger.once("2026-12-31T23:59:59Z")` -- one-shot at a timestamp
- `upstream_job.success` -- chain after another job succeeds (followup trigger)

**Notes:**
- Triggers declared in code are the **source of truth** -- there is no CLI command for adding/removing schedules.
- `dlthub deploy` reconciles all jobs -- new ones are added, removed ones are archived, unchanged ones are left alone.

See [scheduling-triggers.md](scheduling-triggers.md) for the full trigger types table and more examples.

## Step 4: Advanced trigger and scheduling options

See [advanced-patterns.md](advanced-patterns.md) for full examples of each pattern:

- **Followup jobs** -- chain pipelines with `trigger=ingest_job.success`. The transform runs automatically after ingest succeeds. Use when you have non-incremental pipelines that should run in sequence.
- **Scheduler-driven intervals** -- for incremental pipelines, declare `interval={"start": "2026-01-01T00:00:00Z"}` and read `run_context["interval_start"]` / `interval_end` from the scheduler. Runtime handles continuity and refresh resets.
- **Freshness gates** -- `freshness=[upstream.is_fresh]` prevents a job from running until upstream's interval is complete. Use for transforms that shouldn't observe half-loaded data.
- **Refresh cascade** -- a backfill job with `refresh="always"` cascades a full-refresh signal to all downstream jobs without loading data itself.
- **Non-pipeline jobs** -- `@run.job` for general batch work (DQ checks, reports), `@run.interactive` for MCP servers, dashboards, REST APIs.
- **Dependency groups** -- `require={"dependency_groups": ["ibis"]}` installs extra packages only for jobs that need them. Declare groups in `[dependency-groups]` in `pyproject.toml`.
- **Timeouts** -- `execute={"timeout": "6h"}` overrides the default 120-minute limit. Use for backfill or long-running jobs.


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
- One workspace per GitHub account — connecting a new repo replaces existing deployments.

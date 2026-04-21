---
name: deploy-workspace
description: Deploy dlt pipelines to dltHub Platform. Use when the user says "deploy to dltHub", "launch on dltHub", "run on dltHub", "schedule pipeline", or wants to deploy a pipeline or notebook to dltHub.
---

# Deploy to dltHub Platform

If this is a first deployment, complete (`setup-runtime`) and (`prepare-deployment`) first — they set up the workspace, configure credentials, and log in to runtime. Otherwise, continue from here.

## Step 1: Prepare scripts for production

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
If `__deployment__.py` is set up, first run `dlt runtime deploy --dry-run` to preview changes, then **STOP** — show the plan and get approval from the user before deploying.

```bash
dlt runtime deploy  # synchronizes deployment module with runtime
```
Summarize the output (which jobs created/updated/archived)

### Step 2b. Run pipelines and notebooks

```bash
dlt runtime launch my_pipeline.py             # sync code + run batch job once (i.e. pipeline)
dlt runtime serve my_notebook.py             # sync code + run interactive job (i.e. notebook or data app)
```

### Step 2c. Read logs and debug

```bash
dlt runtime logs my_pipeline.py              # check output (use job name or script path)
dlt runtime logs jobs.my_pipeline --follow   # stream logs in real-time
```

After launching:
- Check the first run completes successfully with `dlt runtime logs`
- If it fails, use (`debug-deployment`) to diagnose

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
dlt runtime deploy                    # sync manifest to Runtime
dlt runtime deploy --dry-run          # preview without applying
dlt runtime job list                  # confirm triggers are set
```

**Other trigger types** (from `dlt.hub.run.trigger`):
- `trigger.every("6h")` -- every 6 hours
- `trigger.once("2026-12-31T23:59:59Z")` -- one-shot at a timestamp
- `upstream_job.success` -- chain after another job succeeds (followup trigger)

**Notes:**
- Triggers declared in code are the **source of truth** -- there is no CLI command for adding/removing schedules.
- `dlt runtime deploy` reconciles all jobs -- new ones are added, removed ones are archived, unchanged ones are left alone.

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


## Important

- Scripts must have `if __name__ == "__main__":` or the job does nothing.
- Runtime installs from `pyproject.toml` — add all needed packages (e.g. `uv add numpy pandas` if using `.df()`).
- Jobs are killed after 120 minutes. Overwrite timeout in the decorators for long running (backfill) jobs
- One workspace per GitHub account — connecting a new repo replaces existing deployments.

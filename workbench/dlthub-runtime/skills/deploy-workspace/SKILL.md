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
   - Verify they use `dlt.attach()` (not `dlt.pipeline()`) and that **destination** and **dataset_name** are explicitly passed (this is a temporary limitation of the runtime)
   - All visualization dependencies (`altair`, `ibis-framework`, `pandas`, etc.) are in `pyproject.toml`

## Step 2: Deploy, launch, debug

**Reference**: https://dlthub.com/docs/devel/hub/runtime/overview

```bash
dlt runtime launch my_pipeline.py             # sync code + run batch job once (ie pipeline)
dlt runtime serve my_notebook.py             # sync code + run interactive job (ie. notebook)
dlt runtime sync                             # sync code + config without running anything
dlt runtime logs my_pipeline.py              # check output (use job name or script path)
dlt runtime logs jobs.my_pipeline --follow   # stream logs in real-time
```

After launching:
- Check the first run completes successfully with `dlt runtime logs`
- If it fails, use (`debug-deployment`) to diagnose

## Step 3: Schedule a pipeline (cron)

Scheduling requires a `__deployment__.py` manifest in the project root. `dlt runtime schedule` is documented but not yet implemented — use this approach instead.

Create `__deployment__.py`:

```python
import dlt
from dlt._workspace.deployment.decorators import pipeline_run
from dlt._workspace.deployment.trigger import schedule

from my_pipeline import my_source  # import the @dlt.source function


@pipeline_run("my_pipeline", trigger=schedule("0 0 * * *"))  # daily at midnight UTC
def run_my_pipeline():
    pipeline = dlt.pipeline(
        pipeline_name="my_pipeline",
        destination="warehouse",       # use the named destination
        dataset_name="my_dataset",
    )
    pipeline.run(my_source())
```

Then deploy:

```bash
dlt runtime deploy          # preview: add --dry-run --show-manifest
```

**Other trigger types** (from `dlt._workspace.deployment.trigger`):
- `every("6h")` — every 6 hours
- `deployment()` — run on every code deploy
- `job_success("other_job")` — chain after another job succeeds

**Notes:**
- The function body must recreate the pipeline (not reuse a module-level `pipeline` variable).
- `dlt runtime deploy` reconciles all jobs — new ones are added, removed ones are archived.
- After deploying, use `dlt runtime job list` to confirm the trigger is set.

## Important

- Scripts must have `if __name__ == "__main__":` or the job does nothing.
- Runtime installs from `pyproject.toml` — add all needed packages (e.g. `uv add numpy pandas` if using `.df()`).
- Jobs are killed after 120 minutes. Use incremental loads for long pipelines.
- One workspace per GitHub account — connecting a new repo replaces existing deployments.

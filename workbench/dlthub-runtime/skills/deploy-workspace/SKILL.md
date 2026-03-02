---
name: deploy-workspace
description: Deploy dlt pipelines to dltHub Runtime. Use when the user says "deploy to runtime", "launch on runtime", "run on dlt Hub", or "schedule pipeline". Assumes workspace is verified and production credentials are set up.
---

# Deploy to dltHub Runtime

Assumes (`setup-runtime`) and (`prepare-deployment`) have been completed — workspace is set up, credentials are configured, and runtime login is done.

## Step 1: Prepare scripts for production

Review each script being deployed and fix patterns that are safe locally but harmful in production:

1. **Remove `dev_mode=True`** from `dlt.pipeline()` calls — it drops and recreates the dataset on every run, destroying production data.
2. **Remove or externalize dev limits** — `limit=N` parameters, `.add_limit(N)` calls, or hardcoded date ranges meant for testing. Either remove them or make them configurable (e.g. via `dlt.config.value`).
3. **Verify `write_disposition`** — `"replace"` is fine for full-refresh pipelines, but confirm the user doesn't actually want `"merge"` or `"append"` for incremental loads.
4. **Check `if __name__ == "__main__":` block** — every script must have one or the runtime job does nothing. The block should NOT contain interactive/debug-only code.
5. **Pin the dlt version exactly** in `pyproject.toml` — use `==` not `>=` to prevent unexpected upgrades on runtime. If user has a pre-release (e.g. `1.23.0a2`), use `uv pip install` to install it and pin with `==` in pyproject (do NOT use `uv add` which may downgrade to latest stable).
6. **Notebooks (`marimo` apps)**:
   - Verify they use `dlt.attach()` (not `dlt.pipeline()`) and that **destination** and **dataset_name** are explicitly passed (this is a temporary limitation of the runtime)
   - All visualization dependencies (`altair`, `ibis-framework`, `pandas`, etc.) are in `pyproject.toml`

## Step 2: Deploy, launch, debug

**Reference**: https://dlthub.com/docs/hub/runtime/overview.md

```bash
dlt runtime deploy                             # sync code + config
dlt runtime launch my_pipeline.py              # run batch job once (ie pipeline)
dlt runtime serve my_notebook.py              # run interactive job (ie. notebook)
dlt runtime logs my_pipeline.py                # check output
```


After deploying:
- Check the first run completes successfully with `dlt runtime logs`
- If it fails, use (`debug-deployment`) to diagnose


NOTE: do not put any pipelines on schedule. This part is coming soon

## Important

- Scripts must have `if __name__ == "__main__":` or the job does nothing.
- Runtime installs from `pyproject.toml` — add all needed packages (e.g. `uv add numpy pandas` if using `.df()`).
- Jobs are killed after 120 minutes. Use incremental loads for long pipelines.
- One workspace per GitHub account — connecting a new repo replaces existing deployments.

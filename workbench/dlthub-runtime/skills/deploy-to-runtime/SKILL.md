---
name: deploy-to-runtime
description: Deploys dlt pipelines to dlt Hub Runtime. Use when the user says "deploy to runtime", "launch on runtime", "run on dlt Hub", or "schedule pipeline".
---

# Deploy to dlt Hub Runtime

## Step 1: Setup Python project, add dependencies

Verify `pyproject.toml` exists in the project root. If not, run `uv init` first. Runtime uses it to install dependencies remotely.

```bash
uv add "dlt[workspace,hub]"
touch .dlt/.workspace
```

Make sure that `pyproject.toml` contains dependencies required for running ie. if user has `requirements.txt` - ask user if you should move them or not.


## Step 2: Verify `.dlt/` config structure

Run `ls .dlt/*.toml` to ensure which files exist

```
.dlt/
├── config.toml           # Local dev config
├── secrets.toml          # Local dev secrets (gitignored)
├── .workspace            # enable profiles and runtime cli
```

Files above should exist.

Per profile files **may** exist. You will create some of them in next step:
```
├── prod.config.toml      # Production config
├── prod.secrets.toml     # Production secrets (gitignored)
├── access.config.toml    # Interactive notebook config
└── access.secrets.toml   # Interactive notebook secrets (gitignored)
```

**Reference** https://dlthub.com/docs/hub/core-concepts/profiles-dlthub.md


## Step 3: Set up production credentials

Help user to fill config and secrets for sources and destinations. Help user to keep secrets and config clear.
1. Investigate content of `config.toml` and `secrets.toml` (via `dlt ai secrets view-redacted`). User could put their local (`dev`) settings in workspace-scoped toml files.
2. In that case help user to create a separate `dev` profile scoped settings.
3. Help to create `prod` profiles config and secret files - user should fill right information for their sources and destinations.
4. Verify the whole setup at the end. 


## Step 4: Prepare pipelines and notebooks for production

Review each script being deployed and fix patterns that are safe locally but harmful in production:

1. **Remove `dev_mode=True`** from `dlt.pipeline()` calls — it drops and recreates the dataset on every run, destroying production data.
2. **Remove or externalize dev limits** — `limit=N` parameters, `.add_limit(N)` calls, or hardcoded date ranges meant for testing. Either remove them or make them configurable (e.g. via `dlt.config.value`).
3. **Verify `write_disposition`** — `"replace"` is fine for full-refresh pipelines, but confirm the user doesn't actually want `"merge"` or `"append"` for incremental loads.
4. **Check `if __name__ == "__main__":` block** — every script must have one or the runtime job does nothing. The block should NOT contain interactive/debug-only code.
5. **Pin the dlt version exactly** in `pyproject.toml` — use `==` not `>=` to prevent unexpected upgrades on runtime. If user has a pre-release (e.g. `1.23.0a1`), use `uv pip install` to install it and pin with `==` in pyproject (do NOT use `uv add` which may downgrade to latest stable).
6. **Notebooks (`marimo` apps)**:
- verify they use `dlt.attach()` (not `dlt.pipeline()`) and that **destination** and **dataset_name** are explicitly passed (this is temporary limitation of the runtime)
- all visualization dependencies (`altair`, `ibis-framework`, `pandas`, etc.) are in `pyproject.toml`. 

### Set up production destination
Offer to setup a production destination. If user is using `duckdb` explain why the ingested data will not survive to be visible by notebooks (runtime erases ephemeral storage!). Explain the concept of named destination first!

1. If user is using `duckdb` - offer to set up Motherduck
2. Recommend switching to **named destination**:
- set up right destination types in profile scoped toml files
- change the destination for pipelines being deployed (all scripts - including notebooks).
- setup credentials using profile-scoped secret files. verify the state of the secrets: make sure they overwrite workspace secrets correctly.
- offer to run pipeline locally (preferably in debug mode) to confirm the settings

## Step 5: Login, deploy, launch

**Reference**: https://dlthub.com/docs/hub/runtime/overview.md

```bash
dlt runtime login                              # GitHub OAuth
dlt runtime deploy                             # sync code + config
dlt runtime launch my_pipeline.py              # test run
dlt runtime schedule my_pipeline.py "0 6 * * *"  # optional cron
dlt runtime logs my_pipeline.py                # check output
```

## Important

- Scripts must have `if __name__ == "__main__":` or the job does nothing.
- Runtime installs from `pyproject.toml` — add all needed packages (e.g. `uv add numpy pandas` if using `.df()`).
- Jobs are killed after 120 minutes. Use incremental loads for long pipelines.
- One workspace per GitHub account — connecting a new repo replaces existing deployments.

## Troubleshooting

**Missing dependencies on Runtime**: Ensure all packages are in `pyproject.toml`, not just locally installed.
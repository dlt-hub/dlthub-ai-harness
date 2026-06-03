---
name: prepare-deployment
description: Prepare production credentials and destinations for dltHub Platform. Use when setting up prod profile secrets, splitting dev/prod credentials, or configuring a production destination like Motherduck.
---

# Prepare workspace for production

Set up profile-scoped credentials and production destinations so the runtime can run pipelines with the right config.

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/profiles.md

## 1. Verify `.dlt/` config structure

Run `ls .dlt/*.toml` to see which files exist:

```
.dlt/
├── config.toml           # Workspace config (all profiles)
├── secrets.toml          # Workspace secrets (all profiles, gitignored)
├── .workspace            # Enable profiles and runtime CLI
```

Per-profile files **may** exist. You will create some of them below:
```
├── dev.config.toml       # Dev-only config
├── dev.secrets.toml      # Dev-only secrets (gitignored)
├── prod.config.toml      # Production config
├── prod.secrets.toml     # Production secrets (gitignored)
├── access.config.toml    # Interactive notebook config
└── access.secrets.toml   # Interactive notebook secrets (gitignored)
```

## 2. Split dev/prod secrets

Use `secrets_list`, `secrets_view_redacted`, and `secrets_update_fragment` MCP tools (or `dlthub ai secrets` CLI as fallback) — see (`setup-secrets`) skill for details.

1. Use `secrets_list` to see all secret files. Then `secrets_view_redacted` (no path) for the unified merged view, or with `path` to inspect individual files.
2. If user has put dev-only settings in workspace-scoped toml files, help them split: move dev-only settings into a `dev` profile file via `secrets_update_fragment` with `path=".dlt/dev.secrets.toml"`.
3. Help create `prod` profile secrets via `secrets_update_fragment` with `path=".dlt/prod.secrets.toml"` — user should fill in production values for their sources and destinations.
4. Verify the whole setup with `secrets_view_redacted` (unified view) and per-file with `path`.

## 3. Set up production destination

Offer to set up a production destination. If user is using `duckdb`, explain why ingested data will not survive to be visible by notebooks (runtime erases ephemeral storage!).

### 3a. Ask for type of production destination
1. If user is using `duckdb` — offer to set up **Motherduck** as the production destination.
2. `dlt` supports most major warehouses, data lakes and pure filesystems.

**If transformations are part of this workspace and the production destination differs from dev:** before proceeding, run the (`debug-transformation`) skill from the **transformations** toolkit to validate SQL dialect compatibility. Transformations developed against DuckDB may use syntax that fails on BigQuery, Snowflake, or Postgres.

### 3b. Configure production destination

Our goal here is to keep **existing dev destination** in dev profile, and configure **production** destination
in prod profile. User will be able to continue development as usual while deploying - with the same code!

Learn the concept of **named destinations** first:
- **Reference**: https://dlthub.com/docs/general-usage/destination.md
- named destination is like alias - may refer to duckdb on **dev** and **motherduck** on prod.
- you use name of destination (ie. **warehouse**), instead of type

Recommend to user switching to a named destination:
   - Pick destination $name
   - Set up the right destination types in profile-scoped toml files for that $name (**MUST** read the reference!)
   - Change the `destination` to $name for pipelines being deployed (all scripts — including notebooks)
   - Set up credentials using profile-scoped secret files. Verify the state of secrets: make sure they overwrite workspace secrets correctly
   - Offer to run pipeline locally (preferably in debug mode) to confirm settings. NOTE: pipeline will run on **dev** destination!
   - **DO NOT** run pipeline on **prod** profile. That happens on runtime deployment!

**STOP** before making changes. Show your **plan** and get approval from the user.

### 3c. Verify production destination access (optional)

Skip this step if prod credentials were already configured and verified before this session. Run it when setting up prod credentials for the first time or after changing them.

Read [check_destination.py](check_destination.py) and run it to verify credentials work:
```
uv run python .claude/skills/prepare-deployment/check_destination.py <profile> <destination> [dataset_name]
```

## 4. Verify secrets state

Use `secrets_view_redacted` to see the final unified view across all workspace secret files. Confirm:
- Dev profile has local/test credentials
- Prod profile has production credentials
- No placeholder values remain in prod secrets
- Profile-scoped files correctly override workspace-scoped defaults

## 5. Create deployment manifest (`__deployment__.py`)

**Reference**: [deployment-module.md](deployment-module.md)
**Full Documentation** https://dlthub.com/docs/hub/pipeline-operations/deployments.md

- This step is **optional** for simple workspaces with a single pipeline and notebook -- you can use `dlthub run <file>` directly instead (see the [platform tutorial](https://dlthub.com/docs/hub/getting-started/platform-tutorial.md))
- This step is **mandatory** for workspaces with transformations, multiple pipelines, scheduled jobs, or followup triggers
- This step will be repeated when more notebooks or pipelines are added to the workspace

### 5a. Identify pipeline runs

Find every `dlt.pipeline(...).run(...)` call site that should run on Runtime. Each one becomes a decorated function. Look for:
- Scripts with `if __name__ == "__main__"` blocks that create and run a pipeline
- Transformation scripts that read from one dataset and write to another

### 5b. Decorate with `@run.pipeline`

Wrap each pipeline run in a decorated function. Use `from dlt.hub import run`:

```python
from dlt.hub import run

@run.pipeline("my_pipeline")
def ingest_data():
    pipeline = dlt.pipeline(
        pipeline_name="my_pipeline",
        destination="warehouse",
        dataset_name="my_data",
    )
    pipeline.run(my_source())
```

**DO NOT** add triggers or schedules at this point -- just the bare minimum to register the job. Scheduling is added in the deployment step.

### 5c. Create or update `__deployment__.py`

1. **Import decorated functions** (`from my_pipeline import ingest_data`)
2. **Import notebook modules** (`import my_notebook`)
3. **Add a module docstring** -- first line becomes workspace description
4. **Create `__all__`** listing every name to deploy

```python
"""My workspace -- ingest and explore data"""

from my_pipeline import ingest_data
import my_notebook

__all__ = ["ingest_data", "my_notebook"]
```

5. **Verify**: `dlthub deploy --dry-run` -- shows what would be created/updated/archived
6. **Debug**: `dlthub deploy --show-manifest` -- dumps full manifest as YAML

### Job references

Every deployed job gets a `job_ref` in `jobs.<module>.<function>` form:
- `from my_pipeline import ingest_data` -> `jobs.my_pipeline.ingest_data`
- `import my_notebook` -> `jobs.my_notebook`

**Job names**: bare names work when unambiguous. `dlthub run ingest_data` resolves automatically.

**STOP** before making changes. Show your **plan** and get approval from the user.

Tell the user the workspace is ready for deployment — use (`deploy-workspace`) next.

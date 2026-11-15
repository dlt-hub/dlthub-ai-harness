---
name: prepare-deployment
description: Prepare a workspace for its first deployment. Set up the `prod` profile with production credentials and a production destination, and declare the jobs in `__deployment__.py`. Use when the user wants to deploy for the first time, set up prod profile secrets, split dev and prod credentials, or configure a production destination like MotherDuck.
---

# Prepare workspace for production

Configure the `prod` profile with production credentials and a production destination, and declare the jobs. Then a
deployment runs the jobs with the right config. A platform toolkit deploys them.

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/profiles.md |
https://dlthub.com/docs/hub/pipeline-operations/deployments.md

## 1. Pick the production destination

Offer to set up a production destination. If user is using `duckdb`, explain why ingested data will not survive to
be visible by notebooks: a deployed job runs on a runner whose local storage is lost after the job run.

1. If user is using `duckdb` — offer to set up **MotherDuck** as the production destination.
2. `dlt` supports most major warehouses, data lakes and pure filesystems.

**If transformations are part of this workspace and the production destination differs from dev:** before proceeding, run the (`debug-transformation`) skill from the **transformations** toolkit to validate SQL dialect compatibility. Transformations developed against DuckDB may use syntax that fails on BigQuery, Snowflake, or Postgres.

## 2. Configure the `prod` profile

Use the (`setup-profiles`) skill, use case "DuckDB locally, a warehouse in production". Keep the **existing dev destination** in the `dev` profile. Configure the production destination and its credentials in the `prod` profile. User will be able to continue development as usual while deploying - with the same code! Notebooks run with the `access` profile, and so do agent jobs when `prod` has no profile with `none` data access. Until `access` has settings files, they run with `prod`. Give `access` read-only credentials at the destination, as use case "limit the data access of jobs" says.

- Change the `destination` of every script that you deploy, notebooks included, to the named destination.
- Offer to run pipeline locally (preferably in debug mode) to confirm settings. NOTE: pipeline will run on **dev** destination!
- Run a job with the `prod` profile only after the user agrees: it writes with the production credentials.
- Make sure that no placeholder values remain in the secrets of `prod`.

**STOP** before making changes. Show your **plan** and get approval from the user.

## 3. Declare the jobs (`__deployment__.py`)

**Reference**: [deployment-module.md](../run-local-jobs/deployment-module.md)

- This step is **mandatory** for workspaces with transformations, multiple pipelines, scheduled jobs, or follow-up triggers
- This step will be repeated when more notebooks or pipelines are added to the workspace
- Some platforms also run a single pipeline file without `__deployment__.py`: the platform toolkit says when

### 3a. Identify pipeline runs

Find every `dlt.pipeline(...).run(...)` call site that should run in a deployment. Each one becomes a decorated function. Look for:
- Scripts with `if __name__ == "__main__"` blocks that create and run a pipeline
- Transformation scripts that read from one dataset and write to another

### 3b. Decorate with `@run.pipeline`

Wrap each pipeline run in a decorated function. Create the pipeline inside the function. Use `from dlt.hub import run`:

```python
import dlt
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

**Refresh runs (recommended):** add `auto_refresh_pipeline_mode="drop_sources"` to the decorator, e.g. `@run.pipeline("my_pipeline", auto_refresh_pipeline_mode="drop_sources")`. Then a refresh run (`--refresh`) reloads every pipeline in the job. Without it, a refresh run does not reload the pipeline. Modes and the refresh cascade: `job-patterns.md` of the (`run-local-jobs`) skill, "Refresh runs and the refresh cascade".

### 3c. Create or update `__deployment__.py`

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

5. **Verify**: `dlthub local info` lists the jobs at the end of its output. `dlthub local run <job> --dry-run` resolves
   a job without running it.
6. **Run each job once** with `dlthub local run <job>`, as the (`run-local-jobs`) skill says.

### Job references

Every job gets a `job_ref` in `jobs.<module>.<function>` form:
- `from my_pipeline import ingest_data` -> `jobs.my_pipeline.ingest_data`
- `import my_notebook` -> `jobs.my_notebook`

**Job names**: bare names work when unambiguous. `dlthub local run ingest_data` resolves automatically.

**STOP** before making changes. Show your **plan** and get approval from the user.

Tell the user the workspace is ready for deployment — use the deploy skill of the platform toolkit next.

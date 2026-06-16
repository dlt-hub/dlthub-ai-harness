---
name: deploy-run-sample-pipeline
description: "Test-deploy and run the pre-shipped GitHub issues sample pipeline on dltHub Platform — an educational end-to-end run to try dlthub and see a job on the cloud, NOT a production-grade pipeline. Use when the user wants to try/demo the deploy-and-run flow with the bundled github_pipeline.py. For a real pipeline (your own source, auth, incremental, custom destination, production deploy), use the rest-api-pipeline toolkit (find-source)."
argument-hint: ""
---

Deploy `github_pipeline.py` — already present in the project root — to dltHub Platform. This pipeline loads the 50 most recent issues from `dlt-hub/dlt`.

Do not use when the user wants to deploy a pipeline other than github_pipeline.py, or when github_pipeline.py does not already exist in the project root.

**Scope:** this is a throwaway, educational path for trying dlthub end-to-end. The moment the user wants a real pipeline — their own source, auth beyond a single key, incremental loading, multiple endpoints — hand over to the **rest-api-pipeline** toolkit (`find-source`); don't harden this sample in place.

## Step 1 — Connect to the personal playground workspace

```bash
uv run dlthub workspace connect playground
```

If multiple workspaces named `playground` exist, run `uv run dlthub workspace list` first, pick the personal one (not org-level), then connect to it by name.

Note the workspace ID from the output — you will need it in the final step.

## Step 2 — Choose a destination

Ask the user which destination they want to use:

> Which destination would you like to deploy to?
> 1. MotherDuck
> 2. BigQuery
> 3. Snowflake
> 4. Other

Wait for the user to respond before continuing. If they choose "Other", ask them to type the name in.

## Step 3 — Install destination

Fetch the docs URL for the chosen destination from the [reference table](#destination-docs) at the bottom of this skill. Read it to find the install extra and required credential fields — you will need both in the next step.

Install the package and sync:

```bash
uv add "dlt[<extra>]"
uv sync
```

## Step 4 — Configure credentials

Write the prod credential skeleton using `secrets_update_fragment` with `path=".dlt/prod.secrets.toml"`, using only the credential fields from the docs you just read — do not guess:

```toml
[destination.warehouse]
destination_type = "<chosen-destination>"

[destination.warehouse.credentials]
# fields as documented — do not guess
```

Then tell the user:

> I've created the credential structure in `.dlt/prod.secrets.toml`. Please open that file and fill in your values, then let me know when done.

**Stop and wait** for the user to confirm before continuing.

Use `secrets_view_redacted` to verify — confirm credentials appear as `***`. If any field is still empty, ask the user to fill it in before proceeding.

## Step 5 — Register in `__deployment__.py`

Add the pipeline to the existing `__deployment__.py`:

```python
from github_pipeline import load_github

__all__ = ["load_github"]
```

## Step 6 — Deploy

```bash
uv run dlthub deploy
```

Summarize which jobs were created or updated.

## Step 7 — Run on the cloud

```bash
uv run dlthub run load_github -f
```

The `-f` flag streams logs in real time. Wait for the job to complete.

If it fails:

```bash
uv run dlthub job logs load_github
```

| Error | Cause | Fix |
|---|---|---|
| `Trial period has ended` | Plan expired | Contact your workspace admin |

Once successful, open the dltHub dashboard directly in the user's browser. Substitute `<workspace_id>` with the workspace ID captured in Step 1:

```bash
uv run python -c "import click; click.launch('https://app.dlthub.com/w/<workspace_id>/notebooks/jobs.workspace.dashboard/show')"
```

---

## Destination docs

| Destination | Docs |
|---|---|
| MotherDuck | https://dlthub.com/docs/dlt-ecosystem/destinations/motherduck |
| BigQuery | https://dlthub.com/docs/dlt-ecosystem/destinations/bigquery |
| Snowflake | https://dlthub.com/docs/dlt-ecosystem/destinations/snowflake |
| Athena | https://dlthub.com/docs/dlt-ecosystem/destinations/athena |
| Clickhouse | https://dlthub.com/docs/dlt-ecosystem/destinations/clickhouse |
| Databricks | https://dlthub.com/docs/dlt-ecosystem/destinations/databricks |
| Delta / Iceberg | https://dlthub.com/docs/dlt-ecosystem/destinations/delta-iceberg |
| Dremio | https://dlthub.com/docs/dlt-ecosystem/destinations/dremio |
| DuckDB | https://dlthub.com/docs/dlt-ecosystem/destinations/duckdb |
| DuckLake | https://dlthub.com/docs/dlt-ecosystem/destinations/ducklake |
| Fabric | https://dlthub.com/docs/dlt-ecosystem/destinations/fabric |
| Filesystem | https://dlthub.com/docs/dlt-ecosystem/destinations/filesystem |
| HuggingFace | https://dlthub.com/docs/dlt-ecosystem/destinations/huggingface |
| Iceberg | https://dlthub.com/docs/dlt-ecosystem/destinations/iceberg |
| Lance | https://dlthub.com/docs/dlt-ecosystem/destinations/lance |
| LanceDB | https://dlthub.com/docs/dlt-ecosystem/destinations/lancedb |
| MSSQL | https://dlthub.com/docs/dlt-ecosystem/destinations/mssql |
| Postgres | https://dlthub.com/docs/dlt-ecosystem/destinations/postgres |
| Qdrant | https://dlthub.com/docs/dlt-ecosystem/destinations/qdrant |
| Redshift | https://dlthub.com/docs/dlt-ecosystem/destinations/redshift |
| SQLAlchemy | https://dlthub.com/docs/dlt-ecosystem/destinations/sqlalchemy |
| Synapse | https://dlthub.com/docs/dlt-ecosystem/destinations/synapse |
| Weaviate | https://dlthub.com/docs/dlt-ecosystem/destinations/weaviate |
---
name: deploy-run-sample-pipeline
description: Write, deploy and run a GitHub issues pipeline on dltHub Platform. Use when the user wants to load GitHub issues from dlt-hub/dlt and deploy the pipeline to the cloud.
argument-hint: ""
---

Deploy `github_pipeline.py` — already present in the project root — to dltHub Platform. This pipeline loads the 50 most recent issues from `dlt-hub/dlt`.

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

Wait for the user to respond before continuing.

If they choose "Other", ask them to type the name in and retain their chosen destination in memory.

## Step 3 — Configure Destination

Fetch the docs URL for the chosen destination. Read it to find the install command and the required credential fields — you will need both in the next two steps.

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

Install the package and sync:

```bash
uv add "dlt[<extra>]"
uv sync
```

## Step 3.1 — Configure credentials

Write the prod credential skeleton using `secrets_update_fragment` with `path=".dlt/prod.secrets.toml"`, using only the credential fields from the docs page you just read:

```toml
[destination.warehouse]
destination_type = "<chosen-destination>"

[destination.warehouse.credentials]
# fields as documented for <chosen-destination> — do not guess
```

Then tell the user:

> I've created the credential structure in `.dlt/prod.secrets.toml`. Please open that file and fill in your values, then let me know when done.

**Stop and wait** for the user to confirm before continuing.

Use `secrets_view_redacted` to verify — confirm credentials appear as `***`. If any field is still empty, ask the user to fill it in before proceeding.

## Step 4 — Register in `__deployment__.py`

Add the pipeline to the existing `__deployment__.py`:

```python
from github_pipeline import load_github

__all__ = [..., "load_github"]
```

## Step 5 — Deploy

```bash
uv run dlthub deploy
```

Summarize which jobs were created or updated.

## Step 6 — Run on the cloud

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
